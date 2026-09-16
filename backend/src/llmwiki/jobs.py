"""写入任务队列、状态持久化与 SSE 事件总线（TASK-004）。"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from llmwiki.config import ConfigStore, config_store
from llmwiki.errors import AppError, ErrorCode


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    """一次写入任务的元数据。"""

    id: str = field(default_factory=lambda: f"job-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}")
    kind: str = "generic"
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    total: int = 0
    done: int = 0
    detail: str = ""
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    # 围观页快照的扩展状态（当前素材/页面、步骤列表）；随 jobs.json 持久化。
    meta: dict[str, Any] = field(default_factory=dict)


JobFunc = Callable[[Job], Coroutine[Any, Any, None]]


class JobQueue:
    """全局单写入队列：严格串行执行，并把状态持久化到 vault。"""

    def __init__(self, config_store_override: ConfigStore | None = None) -> None:
        self._queue: asyncio.Queue[tuple[Job, JobFunc]] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._worker_task: asyncio.Task | None = None
        self._config_store_override = config_store_override
        self._recovered = False

    @property
    def config_store(self) -> ConfigStore:
        """返回队列使用的配置仓库，便于测试替换全局配置。"""

        return self._config_store_override or config_store

    @property
    def jobs_file(self) -> Path:
        """返回 vault 内的运行时状态文件路径。"""

        vault_path = self.config_store.load().vault_path
        if not vault_path:
            raise AppError(ErrorCode.VALIDATION, "知识库路径未配置，无法保存任务状态")
        return Path(vault_path).expanduser() / ".llmwiki" / "jobs.json"

    @property
    def running(self) -> bool:
        return any(job.status is JobStatus.RUNNING for job in self._jobs.values())

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def subscriber_count(self) -> int:
        """返回当前 SSE 订阅数量，便于健康检查与测试同步。"""

        return len(self._subscribers)

    @property
    def current_job_id(self) -> str | None:
        for job in self._jobs.values():
            if job.status is JobStatus.RUNNING:
                return job.id
        return None

    @property
    def jobs(self) -> list[Job]:
        """按提交顺序返回任务列表。"""

        self._recover_if_needed()
        return list(self._jobs.values())

    async def submit(self, kind: str, func: JobFunc, total: int = 1) -> Job:
        """提交一个写入任务；繁忙时继续排队。"""

        # 重启后的第一次 submit 也必须保留历史任务，不能让新快照覆盖旧状态。
        self._recover_if_needed()
        if total < 1:
            raise AppError(ErrorCode.VALIDATION, "任务总数必须大于 0", {"total": total})

        # 新任务进入内存后，本次运行时状态比磁盘恢复源更新。
        self._recovered = True
        job = Job(kind=kind, total=total)
        self._jobs[job.id] = job
        await self._persist()
        await self._queue.put((job, func))
        await self._publish(self._job_event(job, "job.progress"))
        self._ensure_worker()
        return job

    def get(self, job_id: str) -> Job | None:
        """查询任务；首次访问时自动恢复历史状态。"""

        self._recover_if_needed()
        return self._jobs.get(job_id)

    def get_or_raise(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job is None:
            raise AppError(ErrorCode.NOT_FOUND, "任务不存在", {"job_id": job_id})
        return job

    async def update_progress(
        self,
        job: Job,
        *,
        progress: float | None = None,
        done: int | None = None,
        detail: str | None = None,
    ) -> None:
        """更新执行中任务进度，并同步持久化与广播。"""

        current = self.get(job.id)
        if current is not job:
            raise AppError(ErrorCode.NOT_FOUND, "任务不存在", {"job_id": job.id})
        if current.status is not JobStatus.RUNNING:
            raise AppError(
                ErrorCode.JOB_CONFLICT,
                "只有执行中的任务可以更新进度",
                {"status": current.status.value},
            )

        if progress is not None:
            current.progress = min(1.0, max(0.0, float(progress)))
        if done is not None:
            if done < 0 or done > max(current.total, 0):
                raise AppError(
                    ErrorCode.VALIDATION,
                    "任务完成数超出范围",
                    {"done": done, "total": current.total},
                )
            current.done = done
            if current.total:
                current.progress = min(1.0, done / current.total)
        if detail is not None:
            current.detail = detail

        await self._persist()
        await self._publish(self._job_event(current, "job.progress"))

    async def publish(self, event: str, **payload: Any) -> None:
        """向所有 SSE 订阅者广播业务事件（例如 lint.ready）。"""

        await self._publish({"event": event, **payload})

    async def subscribe(self) -> AsyncIterator[dict]:
        """注册独立订阅队列；每个 SSE 连接都会收到完整广播。"""

        q: asyncio.Queue[dict] = asyncio.Queue()
        self._subscribers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)

    def current_snapshot_event(self) -> dict | None:
        """连接建立时返回当前任务快照，避免前端等待下一次变化。"""

        self._recover_if_needed()
        job_id = self.current_job_id
        if job_id is None:
            return None
        return self._job_event(self._jobs[job_id], "job.progress")

    def restore(self) -> None:
        """强制从 jobs.json 恢复任务状态。"""

        self._jobs.clear()
        self._queue = asyncio.Queue()
        self._worker_task = None
        self._load_jobs_file()
        self._recovered = True

    async def join(self) -> None:
        """等待队列清空且 worker 完全退出。"""

        await self._queue.join()
        if self._worker_task is not None:
            await self._worker_task

    async def _persist(self) -> None:
        path = self.jobs_file
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "jobs": [self._serialize(job) for job in self._jobs.values()],
        }

        fd, temp_name = tempfile.mkstemp(prefix=".jobs-", suffix=".json.tmp", dir=path.parent)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _serialize(job: Job) -> dict[str, Any]:
        data = asdict(job)
        data["status"] = job.status.value
        return data

    @staticmethod
    def _deserialize(data: dict[str, Any]) -> Job:
        known_fields = Job.__dataclass_fields__  # type: ignore[attr-defined]
        values = {key: value for key, value in data.items() if key in known_fields}
        values["status"] = JobStatus(values.get("status", JobStatus.QUEUED.value))
        return Job(**values)

    def _recover_if_needed(self) -> None:
        if not self._recovered:
            self._load_jobs_file()
            self._recovered = True

    def _load_jobs_file(self) -> None:
        path = self.jobs_file
        if not path.exists():
            return

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise AppError(ErrorCode.VALIDATION, "jobs.json 损坏，无法恢复任务状态") from exc

        items = raw.get("jobs", []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            raise AppError(ErrorCode.VALIDATION, "jobs.json 格式不正确")

        restarted_at = time.time()
        for item in items:
            if not isinstance(item, dict) or "id" not in item:
                continue
            job = self._deserialize(item)
            # 任务函数不进 JSON；重启后未完成任务只能安全地标记为失败。
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                job.status = JobStatus.FAILED
                job.error = job.error or "进程重启导致任务中断"
                job.finished_at = job.finished_at or restarted_at
            self._jobs[job.id] = job

    def _ensure_worker(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker())

    async def _worker(self) -> None:
        while True:
            try:
                job, func = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                self._worker_task = None
                return

            job.status = JobStatus.RUNNING
            job.started_at = time.time()
            await self._persist()
            await self._publish(self._job_event(job, "job.progress"))
            try:
                await func(job)
                job.status = JobStatus.DONE
                job.progress = 1.0
                job.done = job.total
                job.detail = job.detail or "completed"
                await self._persist()
                await self._publish(self._job_event(job, "job.done"))
            except Exception as exc:
                job.status = JobStatus.FAILED
                job.error = str(exc) or exc.__class__.__name__
                await self._persist()
                await self._publish(self._job_event(job, "job.failed"))
            finally:
                job.finished_at = time.time()
                await self._persist()
                self._queue.task_done()

    @staticmethod
    def _job_event(job: Job, event: str) -> dict:
        return {
            "event": event,
            "job_id": job.id,
            "kind": job.kind,
            "status": job.status.value,
            "progress": job.progress,
            "total": job.total,
            "done": job.done,
            "detail": job.detail,
            "error": job.error,
        }

    async def _publish(self, event: dict) -> None:
        for q in self._subscribers:
            q.put_nowait(event)


job_queue = JobQueue()
