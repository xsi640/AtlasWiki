"""设置接口（API-037 ~ API-040）。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from llmwiki.config import config_store
from llmwiki.errors import AppError, ErrorCode

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings() -> dict:
    s = config_store.load()
    return {
        "vault_path": s.vault_path,
        "llm": {
            "provider": s.llm.provider,
            "base_url": s.llm.base_url,
            "model": s.llm.model,
            "has_key": bool(s.llm.api_key),
            "timeout_s": s.llm.timeout_s,
            "max_cost_per_task_usd": s.llm.max_cost_per_task_usd,
        },
        "git": {
            "auto_commit": s.git.auto_commit,
            "auto_push": s.git.auto_push,
            "remote_name": s.git.remote_name,
            "has_remote": False,
        },
    }


class UpdateSettingsRequest(BaseModel):
    vault_path: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None


@router.put("")
async def update_settings(body: UpdateSettingsRequest) -> dict:
    s = config_store.load()
    if body.vault_path is not None:
        s.vault_path = body.vault_path
    if body.llm_base_url is not None:
        s.llm.base_url = body.llm_base_url
    if body.llm_model is not None:
        s.llm.model = body.llm_model
    if body.llm_api_key is not None:
        s.llm.api_key = body.llm_api_key
    config_store.save(s)
    return await get_settings()


@router.post("/git/sync")
async def git_sync() -> dict:
    """手动推送（ADR-009），无远端时返回 E_GIT_FAILED。"""
    raise AppError(ErrorCode.GIT_FAILED, "未配置远端", {"stderr": "fatal: no remote configured"})


@router.get("/costs")
async def get_costs() -> dict:
    return {"entries": [], "total_usd": 0, "currency": "USD"}
