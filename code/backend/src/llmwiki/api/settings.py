"""设置、成本与系统同步接口（TASK-032）。"""

from __future__ import annotations

import configparser
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from llmwiki.config import Settings, config_store
from llmwiki.errors import AppError, ErrorCode
from llmwiki.llm.cost import get_cost_summary
from llmwiki.llm.cost import get_costs as get_cost_records

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _key_hint(value: str) -> str:
    """只暴露 key 的末 4 位；短 key 也不能原样回显。"""
    if not value:
        return ""
    return value[-4:] if len(value) >= 4 else "•" * len(value)


def _has_remote(vault_path: str, remote_name: str) -> bool:
    """读取 vault 的 git config，避免 GET settings 时隐式执行 git init。"""
    if not vault_path:
        return False
    config_path = Path(vault_path).expanduser() / ".git" / "config"
    if not config_path.is_file():
        return False

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(config_path, encoding="utf-8")
    except (OSError, configparser.Error):
        return False
    return any(section == f'remote "{remote_name}"' for section in parser.sections())


def _settings_payload(settings: Settings) -> dict[str, Any]:
    return {
        "vault_path": settings.vault_path,
        "llm": {
            "provider": settings.llm.provider,
            "base_url": settings.llm.base_url,
            "model": settings.llm.model,
            "has_key": bool(settings.llm.api_key),
            "key_hint": _key_hint(settings.llm.api_key),
            "timeout_s": settings.llm.timeout_s,
            "max_cost_per_task_usd": settings.llm.max_cost_per_task_usd,
        },
        "git": {
            "auto_commit": settings.git.auto_commit,
            "auto_push": settings.git.auto_push,
            "remote_name": settings.git.remote_name,
            "has_remote": _has_remote(settings.vault_path, settings.git.remote_name),
        },
    }


@router.get("")
async def get_settings() -> dict[str, Any]:
    """读取设置；API key 只返回 has_key 和 key_hint。"""
    return _settings_payload(config_store.load())


class UpdateSettingsRequest(BaseModel):
    """扁平字段便于设置表单做部分更新；空 key 表示保留旧 key。"""

    vault_path: str | None = None
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_timeout_s: int | None = None
    llm_max_cost_per_task_usd: float | None = None
    git_auto_commit: bool | None = None
    git_auto_push: bool | None = None
    git_remote_name: str | None = None


@router.put("")
async def update_settings(body: UpdateSettingsRequest) -> dict[str, Any]:
    """保存设置；空 API key 不清除旧值，避免只改其他字段时误丢密钥。"""
    settings = config_store.load()
    if body.vault_path is not None:
        settings.vault_path = body.vault_path
    if body.llm_provider is not None:
        settings.llm.provider = body.llm_provider
    if body.llm_base_url is not None:
        settings.llm.base_url = body.llm_base_url
    if body.llm_model is not None:
        settings.llm.model = body.llm_model
    if body.llm_api_key:  # 空串和 None 都保留旧值。
        settings.llm.api_key = body.llm_api_key
    if body.llm_timeout_s is not None:
        if body.llm_timeout_s <= 0:
            raise AppError(
                ErrorCode.VALIDATION,
                "timeout_s 必须大于 0",
                {"fields": [{"field": "llm_timeout_s", "reason": "必须大于 0"}]},
            )
        settings.llm.timeout_s = body.llm_timeout_s
    if body.llm_max_cost_per_task_usd is not None:
        if body.llm_max_cost_per_task_usd < 0:
            raise AppError(
                ErrorCode.VALIDATION,
                "单任务成本上限不能为负数",
                {"fields": [{"field": "llm_max_cost_per_task_usd", "reason": "不能为负数"}]},
            )
        settings.llm.max_cost_per_task_usd = body.llm_max_cost_per_task_usd
    if body.git_auto_commit is not None:
        settings.git.auto_commit = body.git_auto_commit
    if body.git_auto_push is not None:
        settings.git.auto_push = body.git_auto_push
    if body.git_remote_name is not None:
        normalized_remote = body.git_remote_name.strip()
        if not normalized_remote:
            raise AppError(
                ErrorCode.VALIDATION,
                "git remote 名称不能为空",
                {"fields": [{"field": "git_remote_name", "reason": "必填"}]},
            )
        settings.git.remote_name = normalized_remote

    config_store.save(settings)
    return await get_settings()


def _chat_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


@router.post("/test-connection")
async def test_connection() -> dict[str, Any]:
    """发送最小 Chat Completions 请求，并区分鉴权失败与网络超时。"""
    llm = config_store.load().llm
    if not llm.api_key.strip():
        raise AppError(
            ErrorCode.LLM_NOT_CONFIGURED,
            "LLM API key 未配置",
            {"base_url": llm.base_url},
        )

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(llm.timeout_s)) as client:
            response = await client.post(
                _chat_url(llm.base_url),
                json={
                    "model": llm.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "stream": False,
                },
                headers={"Authorization": f"Bearer {llm.api_key}"},
            )
    except httpx.TimeoutException as exc:
        return {
            "ok": False,
            "message": "LLM 连接超时",
            "status": "timeout",
            "timeout_s": llm.timeout_s,
            "detail": str(exc),
        }
    except httpx.HTTPError as exc:
        return {
            "ok": False,
            "message": "无法连接 LLM 服务",
            "status": "connection_failed",
            "detail": str(exc),
        }

    if response.status_code in (401, 402, 403):
        return {
            "ok": False,
            "message": "LLM 鉴权失败或余额不足",
            "status": "auth_failed",
            "status_code": response.status_code,
        }
    if response.status_code == 429:
        return {
            "ok": False,
            "message": "LLM 请求被限流",
            "status": "rate_limited",
            "status_code": response.status_code,
        }
    if response.is_success:
        return {
            "ok": True,
            "message": "LLM 连接成功",
            "status": "ok",
            "status_code": response.status_code,
        }

    return {
        "ok": False,
        "message": "LLM 端点返回错误",
        "status": "request_failed",
        "status_code": response.status_code,
        "detail": response.text[:500],
    }


@router.post("/git/sync")
async def git_sync() -> dict[str, Any]:
    """手动推送（ADR-009），无远端时返回 E_GIT_FAILED。"""
    from llmwiki.audit import GitOperations

    settings = config_store.load()
    result = GitOperations().sync(
        vault_path=settings.vault_path,
        remote_name=settings.git.remote_name,
    )
    return {"ok": True, "stdout": result.stdout, "stderr": result.stderr}


def _cost_entries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for record in records:
        entry: dict[str, Any] = {
            "model": str(record.get("model", "")),
            "input_tokens": int(record.get("input_tokens", 0)),
            "output_tokens": int(record.get("output_tokens", 0)),
            "cost_usd": float(record.get("cost", 0)),
            "source": str(record.get("operation", "llm")),
            "created_at": str(record.get("at", "")),
            "pricing_source": str(record.get("pricing_source", "builtin")),
        }
        if record.get("job_id") is not None:
            entry["job_id"] = str(record["job_id"])
        entries.append(entry)
    return entries


def _bucket_map(
    records: list[dict[str, Any]],
    key_name: str,
    key_extractor: Callable[[dict[str, Any]], Any],
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for record in records:
        key = str(key_extractor(record))
        item = buckets.setdefault(key, {"cost": 0.0, "calls": 0})
        item["cost"] = round(item["cost"] + float(record.get("cost", 0)), 8)
        item["calls"] += 1
    return [{key_name: key, **value} for key, value in sorted(buckets.items())]


@router.get("/costs")
async def get_costs() -> dict[str, Any]:
    """返回完整流水和按日 / 按操作聚合，供成本看板直接使用。"""
    records = await get_cost_records()
    entries = _cost_entries(records)
    summary = await get_cost_summary()
    pricing_source = (
        "custom"
        if any(entry["pricing_source"] == "custom" for entry in entries)
        or summary["pricing_source"] == "custom"
        else "builtin"
    )
    return {
        "entries": entries,
        "total_usd": round(sum(float(record.get("cost", 0)) for record in records), 8),
        "currency": "USD",
        "pricing_source": pricing_source,
        "by_day": _bucket_map(records, "date", lambda record: str(record.get("at", ""))[:10]),
        "by_operation": _bucket_map(
            records,
            "operation",
            lambda record: record.get("operation", "llm"),
        ),
    }


@router.get("/costs/summary")
async def get_cost_summary_api() -> dict[str, Any]:
    """保留 summary 视图，方便前端复用 llm.cost 的权威聚合。"""
    return await get_cost_summary()
