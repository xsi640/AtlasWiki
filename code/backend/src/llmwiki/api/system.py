"""系统接口（API-001 ~ API-003）。"""

from __future__ import annotations

import subprocess

from fastapi import APIRouter
from pydantic import BaseModel

from llmwiki.config import config_store
from llmwiki.errors import AppError, ErrorCode

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/bootstrap")
async def bootstrap() -> dict:
    """冷启动探测：判定空库（BRANCH-001）、待处理体检数与失败素材数。"""
    from pathlib import Path

    settings = config_store.load()
    vault = Path(settings.vault_path) if settings.vault_path else None
    wiki_dir = vault / "wiki" if vault else None
    page_count = len(list(wiki_dir.rglob("*.md"))) if wiki_dir and wiki_dir.exists() else 0
    return {
        "vault_initialized": bool(vault and vault.exists()),
        "is_empty": page_count == 0,
        "page_count": page_count,
        "pending_lint_count": 0,
        "failed_source_count": 0,
        "stale_source_count": 0,
    }


class OpenFolderResponse(BaseModel):
    opened: bool
    path: str


@router.post("/open-folder")
async def open_folder() -> OpenFolderResponse:
    """用系统文件管理器打开 vault 目录（TASK-TBD-003）。"""
    import sys

    settings = config_store.load()
    vault_path = settings.vault_path
    if not vault_path:
        raise AppError(ErrorCode.VALIDATION, "未配置 vault 路径", {"fields": [{"field": "vault_path", "reason": "必填"}]})
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", vault_path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", vault_path])
        else:
            subprocess.Popen(["xdg-open", vault_path])
    except Exception as exc:
        raise AppError(ErrorCode.VALIDATION, f"无法打开文件夹: {exc}") from exc
    return OpenFolderResponse(opened=True, path=vault_path)
