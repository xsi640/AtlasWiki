"""体检接口（API-033 ~ API-036）。路由骨架，服务层由 Wave 4 实现。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/lint", tags=["lint"])


@router.get("/report")
async def get_report() -> dict:
    return {"generated_at": "", "issues": []}


@router.post("/run")
async def run_lint() -> dict:
    return {"job_id": None}


@router.post("/issues/{issue_id}/ignore")
async def ignore_issue(issue_id: str) -> dict:
    return {"ok": True}


@router.post("/issues/{issue_id}/fix")
async def fix_issue(issue_id: str) -> dict:
    return {"job_id": None}
