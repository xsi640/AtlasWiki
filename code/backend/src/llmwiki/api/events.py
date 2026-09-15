"""GET /api/events：SSE 广播端点与心跳生成器（TASK-004）。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from llmwiki.jobs import JobQueue, job_queue

router = APIRouter(tags=["events"])

HEARTBEAT_INTERVAL_S = 15.0


async def heartbeat_generator(interval: float = HEARTBEAT_INTERVAL_S) -> AsyncIterator[str]:
    """按固定间隔产生 SSE 注释行，保持浏览器和代理连接活跃。"""

    if interval <= 0:
        raise ValueError("heartbeat interval must be greater than zero")
    while True:
        await asyncio.sleep(interval)
        yield ":heartbeat\n\n"


def format_sse(event: dict) -> str:
    """把内部事件格式化为标准 SSE data frame。"""

    event_name = str(event.get("event", "message"))
    data = {key: value for key, value in event.items() if key != "event"}
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def _next_event(subscription: AsyncIterator[dict]) -> dict:
    return await subscription.__anext__()


async def event_stream(
    queue: JobQueue,
    *,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_S,
) -> AsyncIterator[str]:
    """合并任务事件与心跳；两个生成器并行推进，互不阻塞。"""

    yield ":connected\n\n"
    snapshot = queue.current_snapshot_event()
    if snapshot is not None:
        yield format_sse(snapshot)

    subscription = queue.subscribe()
    event_task = asyncio.create_task(_next_event(subscription))
    heartbeat_task = asyncio.create_task(_next_event(heartbeat_generator(heartbeat_interval)))
    try:
        while True:
            done, _ = await asyncio.wait(
                {event_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                if task is event_task:
                    yield format_sse(task.result())
                    event_task = asyncio.create_task(_next_event(subscription))
                else:
                    yield task.result()
                    heartbeat_task = asyncio.create_task(
                        _next_event(heartbeat_generator(heartbeat_interval))
                    )
    finally:
        event_task.cancel()
        heartbeat_task.cancel()
        await asyncio.gather(event_task, heartbeat_task, return_exceptions=True)


@router.get("/api/events")
async def events() -> StreamingResponse:
    """广播队列进度和业务事件，并每 15 秒发送一次心跳。"""

    return StreamingResponse(
        event_stream(job_queue, heartbeat_interval=HEARTBEAT_INTERVAL_S),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
