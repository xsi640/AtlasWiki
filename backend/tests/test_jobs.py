"""TASK-004：写入队列持久化与 SSE 事件总线行为测试。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path
from typing import Any

import pytest

from llmwiki.api import events as events_api
from llmwiki.config import Settings
from llmwiki.jobs import Job, JobQueue, JobStatus


class FakeConfigStore:
    def __init__(self, vault_path: Path) -> None:
        self._settings = Settings(vault_path=str(vault_path))

    def load(self) -> Settings:
        return self._settings


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    return tmp_path / "vault"


@pytest.fixture
def queue(vault: Path) -> JobQueue:
    return JobQueue(FakeConfigStore(vault))


async def test_ten_writes_execute_without_overlapping_intervals(queue: JobQueue) -> None:
    started: list[float] = []
    finished: list[float] = []

    async def write(_job: Job) -> None:
        started.append(time.monotonic())
        await asyncio.sleep(0.02)
        finished.append(time.monotonic())

    jobs = [await queue.submit("write", write) for _ in range(10)]
    await queue.join()

    assert len(started) == len(finished) == 10
    assert all(job.status is JobStatus.DONE for job in jobs)
    for previous_end, next_start in zip(finished, started[1:], strict=False):
        assert next_start >= previous_end


async def test_progress_is_queryable_and_matches_jobs_file(queue: JobQueue, vault: Path) -> None:
    gate = asyncio.Event()

    async def compile_pages(job: Job) -> None:
        await queue.update_progress(job, done=1, detail="第一页完成")
        await gate.wait()

    job = await queue.submit("compile", compile_pages, total=4)
    for _ in range(200):
        snapshot = queue.get(job.id)
        if snapshot.status is JobStatus.RUNNING and snapshot.progress == pytest.approx(0.25):
            break
        await asyncio.sleep(0.005)

    current = queue.get_or_raise(job.id)
    assert current.status is JobStatus.RUNNING
    assert current.done == 1
    assert current.detail == "第一页完成"

    payload = json.loads((vault / ".llmwiki" / "jobs.json").read_text("utf-8"))
    persisted = payload["jobs"][0]
    assert persisted["id"] == job.id
    assert persisted["status"] == current.status.value
    assert persisted["progress"] == pytest.approx(current.progress)
    assert persisted["done"] == current.done
    assert persisted["detail"] == current.detail

    gate.set()
    await queue.join()
    payload = json.loads((vault / ".llmwiki" / "jobs.json").read_text("utf-8"))
    assert payload["jobs"][0]["status"] == JobStatus.DONE.value
    assert payload["jobs"][0]["progress"] == pytest.approx(1.0)


async def test_failed_job_is_persisted(queue: JobQueue, vault: Path) -> None:
    async def failed(_job: Job) -> None:
        raise RuntimeError("disk is read only")

    job = await queue.submit("write", failed)
    await queue.join()

    restored = queue.get_or_raise(job.id)
    assert restored.status is JobStatus.FAILED
    assert restored.error == "disk is read only"
    payload = json.loads((vault / ".llmwiki" / "jobs.json").read_text("utf-8"))
    assert payload["jobs"][0]["status"] == JobStatus.FAILED.value
    assert payload["jobs"][0]["error"] == "disk is read only"


async def test_sse_sends_job_progress_and_initial_snapshot(
    queue: JobQueue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(events_api, "job_queue", queue)

    async def work(job: Job) -> None:
        await queue.update_progress(job, progress=0.5)

    response = await events_api.events()
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache, no-store"
    assert response.headers["connection"] == "keep-alive"

    chunks: list[str] = [await response.body_iterator.__anext__()]
    assert chunks[0] == ":connected\n\n"

    # 先让订阅进入等待状态，再提交任务，避免 worker 在订阅前完成。
    reader = asyncio.create_task(response.body_iterator.__anext__())
    for _ in range(100):
        if queue.subscriber_count:
            break
        await asyncio.sleep(0)
    await queue.submit("compile", work)

    while True:
        chunks.append(await asyncio.wait_for(reader, timeout=0.2))
        if '"progress":0.5' in "".join(chunks):
            break
        reader = asyncio.create_task(response.body_iterator.__anext__())

    await response.body_iterator.aclose()

    body = "".join(chunks)
    assert ":connected" in body
    assert "event: job.progress" in body
    assert '"progress":0.5' in body


async def test_sse_heartbeat_generator_runs_independently() -> None:
    stream = events_api.heartbeat_generator(0.01)
    heartbeat = await asyncio.wait_for(stream.__anext__(), timeout=0.2)
    assert heartbeat == ":heartbeat\n\n"
    await stream.aclose()


async def test_event_stream_merges_parallel_heartbeat_and_events(queue: JobQueue) -> None:
    stream = events_api.event_stream(queue, heartbeat_interval=0.01)
    assert await stream.__anext__() == ":connected\n\n"

    # 让生成器先创建事件等待任务，再广播，验证不是通过轮询合并。
    event_reader = asyncio.create_task(stream.__anext__())
    for _ in range(100):
        if queue.subscriber_count:
            break
        await asyncio.sleep(0)
    await queue.publish("lint.ready", pending_count=3)

    frames = [await asyncio.wait_for(event_reader, timeout=0.2)]
    for _ in range(2):
        frames.append(await asyncio.wait_for(stream.__anext__(), timeout=0.2))

    event_frame = next(frame for frame in frames if frame.startswith("event:"))
    assert event_frame.startswith("event: lint.ready\n")
    assert '"pending_count":3' in event_frame

    heartbeat = next(frame for frame in frames if frame.startswith(":"))
    assert heartbeat == ":heartbeat\n\n"
    await stream.aclose()
    assert queue.subscriber_count == 0


async def test_multiple_subscribers_each_receive_broadcast(queue: JobQueue) -> None:
    first = queue.subscribe()
    second = queue.subscribe()

    # 进入两个 async generator 后才完成订阅。
    first_task = asyncio.create_task(first.__anext__())
    second_task = asyncio.create_task(second.__anext__())
    await asyncio.sleep(0)
    await queue.publish("source.status", id="src-1", status="ready")

    first_event, second_event = await asyncio.gather(first_task, second_task)
    assert first_event == second_event
    assert first_event["event"] == "source.status"
    await first.aclose()
    await second.aclose()


async def test_unfinished_jobs_are_recovered_as_failed_after_restart(
    queue: JobQueue,
    vault: Path,
) -> None:
    release = asyncio.Event()

    async def interrupted(job: Job) -> None:
        await queue.update_progress(job, progress=0.4)
        await release.wait()

    job = await queue.submit("compile", interrupted)
    for _ in range(200):
        snapshot = queue.get(job.id)
        if snapshot.status is JobStatus.RUNNING and snapshot.progress == pytest.approx(0.4):
            break
        await asyncio.sleep(0.005)

    # 模拟进程重启：不清理内存状态，仅用同一份配置重新实例化队列。
    restarted_queue = JobQueue(FakeConfigStore(vault))
    restored = restarted_queue.get_or_raise(job.id)

    assert restored.status is JobStatus.FAILED
    assert restored.progress == pytest.approx(0.4)
    assert restored.error == "进程重启导致任务中断"
    assert restored.started_at is not None
    assert restored.finished_at is not None

    release.set()
    with contextlib.suppress(asyncio.CancelledError):
        await queue.join()


async def test_restore_reloads_jobs_file(queue: JobQueue, vault: Path) -> None:
    path = vault / ".llmwiki" / "jobs.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "id": "job-existing",
                        "kind": "compile",
                        "status": "done",
                        "progress": 1.0,
                        "total": 4,
                        "done": 4,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    queue.restore()
    restored = queue.get_or_raise("job-existing")
    assert restored.status is JobStatus.DONE
    assert restored.progress == pytest.approx(1.0)


async def test_submit_after_restart_preserves_previous_jobs(queue: JobQueue, vault: Path) -> None:
    path = vault / ".llmwiki" / "jobs.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [{"id": "job-old", "kind": "write", "status": "done", "progress": 1.0}],
            }
        ),
        encoding="utf-8",
    )

    async def write(_job: Job) -> None:
        pass

    await queue.submit("write", write)
    await queue.join()

    payload = json.loads(path.read_text("utf-8"))
    assert [job["id"] for job in payload["jobs"]] == ["job-old", queue.jobs[-1].id]


async def test_queue_requires_vault_path() -> None:
    class EmptyConfig:
        def load(self) -> Any:
            return Settings(vault_path="")

    empty_queue = JobQueue(EmptyConfig())  # type: ignore[arg-type]
    with pytest.raises(Exception, match="知识库路径未配置"):
        empty_queue.jobs_file.expanduser()
