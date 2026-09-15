"""编译接口（API-024 ~ API-027）。路由骨架，服务层由 G3 实现。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["compile"])


@router.post("/compile")
async def trigger_compile(body: dict) -> dict:
    return {"job_id": None, "queued_sources": 0}


@router.get("/compile/current")
async def current_job() -> dict:
    return {"job_id": None, "status": "idle"}


@router.get("/changes")
async def get_changes(job_id: str | None = None) -> dict:
    return {"job_id": "", "status": "idle", "items": [], "failed_sources": []}
