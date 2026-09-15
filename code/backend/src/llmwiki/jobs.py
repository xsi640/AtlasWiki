"""写入任务队列 + SSE 事件总线（契约层，TASK-004 实现）。"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


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


JobFunc = Callable[[Job], Coroutine[Any, Any, None]]


class JobQueue:
    """全局单写入队列：同一时刻只有一个任务执行。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[Job, JobFunc]] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._jobs: dict[str, Job] = {}
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._worker_task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return any(j.status is JobStatus.RUNNING for j in self._jobs.values())

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def current_job_id(self) -> str | None:
        for j in self._jobs.values():
            if j.status is JobStatus.RUNNING:
                return j.id
        return None

    async def submit(self, kind: str, func: JobFunc, total: int = 1) -> Job:
        job = Job(kind=kind, total=total)
        self._jobs[job.id] = job
        await self._queue.put((job, func))
        self._ensure_worker()
        await self._publish({"event": "job.queued", "job_id": job.id, "kind": kind})
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue()
        self._subscribers.add(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            self._subscribers.discard(q)

    async def _publish(self, event: dict) -> None:
        for q in self._subscribers:
            await q.put(event)

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
            await self._publish({"event": "job.progress", "job_id": job.id, "status": "running", "progress": 0})
            try:
                await func(job)
                job.status = JobStatus.DONE
                job.progress = 1.0
                await self._publish({"event": "job.done", "job_id": job.id, "progress": 1.0})
            except Exception as exc:
                job.status = JobStatus.FAILED
                job.error = str(exc)
                await self._publish({"event": "job.failed", "job_id": job.id, "error": str(exc)})
            finally:
                job.finished_at = time.time()
                self._queue.task_done()


job_queue = JobQueue()
