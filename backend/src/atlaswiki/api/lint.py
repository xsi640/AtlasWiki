"""体检接口（API-033 ~ API-036）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.lint import LintService

router = APIRouter(prefix="/api/lint", tags=["lint"])


@router.get("/report")
async def get_report() -> dict[str, Any]:
    """返回报告；首次访问时生成只读体检报告。"""

    return await LintService().get_report()


@router.post("/run")
async def run_lint() -> dict[str, str]:
    """提交一次串行只读体检任务。"""

    job = await LintService().run_lint()
    return {"job_id": job.id}


@router.post("/issues/{issue_id}/ignore")
async def ignore_issue(issue_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """忽略指定问题；原因是必填字段。"""

    reason = body.get("reason") if isinstance(body, dict) else None
    if not isinstance(reason, str) or not reason.strip():
        raise AppError(
            ErrorCode.VALIDATION,
            "忽略原因不能为空",
            {"fields": [{"field": "reason", "reason": "必填"}]},
        )
    return await LintService().ignore_issue(issue_id, reason)


@router.post("/issues/{issue_id}/fix")
async def fix_issue(issue_id: str) -> dict[str, str]:
    """提交一个结构性问题修复任务。"""

    job = await LintService().fix_issue(issue_id)
    return {"job_id": job.id}
