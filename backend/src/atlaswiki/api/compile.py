"""编译与变更清单接口（API-024 ~ API-027）。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from atlaswiki.compile import CompileEngine
from atlaswiki.config import config_store
from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.jobs import Job, JobStatus, job_queue
from atlaswiki.llm.cost import read_job_cost
from atlaswiki.schema import MaterialStatus
from atlaswiki.workspace.store import WikiStore

router = APIRouter(prefix="/api", tags=["compile"])

_MANIFEST_KINDS = {"created", "updated", "zone_changed"}


def _vault() -> WikiStore:
    settings = config_store.load()
    if not settings.vault_path:
        raise AppError(
            ErrorCode.VALIDATION,
            "尚未配置 vault 路径",
            {"fields": [{"field": "vault_path", "reason": "必填"}]},
        )
    store = WikiStore(Path(settings.vault_path).expanduser().resolve())
    if not store.initialized:
        raise AppError(ErrorCode.NOT_FOUND, "vault 不存在或尚未初始化")
    return store


def _pending_source_ids(store: WikiStore) -> list[str]:
    """待编译素材：从未编译过的 normal，加上编辑后变 stale 的素材。"""

    ids: list[str] = []
    raw_dir = store.vault / "raw"
    if not raw_dir.is_dir():
        return ids
    for path in sorted(raw_dir.glob("*.md")):
        document = store.read_markdown(path.relative_to(store.vault))
        status = str(document.metadata.get("status", MaterialStatus.NORMAL.value))
        if status not in {MaterialStatus.NORMAL.value, MaterialStatus.STALE.value}:
            continue
        if status == MaterialStatus.NORMAL.value and document.metadata.get("compiled_at"):
            continue
        source_id = str(document.metadata.get("id") or path.stem)
        ids.append(source_id)
    return ids


def _iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="milliseconds")


def _snapshot(job: Job) -> dict[str, Any]:
    """把队列任务转换为围观页契约中的 JobSnapshot。"""

    meta = job.meta or {}
    store_vault = None
    settings = config_store.load()
    if settings.vault_path:
        store_vault = Path(settings.vault_path).expanduser()
    total_cost = read_job_cost(store_vault, job.id) if store_vault else 0.0
    return {
        "job_id": job.id,
        "status": job.status.value,
        "kind": job.kind,
        "total_sources": job.total,
        "done_sources": job.done,
        "current_source": meta.get("current_source"),
        "current_page": meta.get("current_page"),
        "steps": meta.get("steps", []),
        "cost": {"currency": "USD", "total": total_cost},
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "failure_reason": job.error,
        "can_leave": True,
    }


def _compile_jobs() -> list[Job]:
    return [job for job in job_queue.jobs if job.kind == "compile"]


@router.post("/compile")
async def trigger_compile(body: dict | None = None) -> dict:
    """对指定素材或全部待编译素材发动编译（API-024）。"""

    if body is not None and not isinstance(body, dict):
        raise AppError(ErrorCode.VALIDATION, "请求体必须是 JSON 对象")
    body = body or {}
    store = _vault()

    source_ids = body.get("source_ids")
    all_pending = body.get("all_pending")
    if source_ids not in (None, []) and not isinstance(source_ids, list):
        raise AppError(
            ErrorCode.VALIDATION,
            "source_ids 必须是字符串数组",
            {"fields": [{"field": "source_ids", "reason": "必须是数组"}]},
        )

    if source_ids:
        normalized: list[str] = []
        for item in source_ids:
            if not isinstance(item, str) or not item.strip():
                raise AppError(
                    ErrorCode.VALIDATION,
                    "source_id 不能为空",
                    {"fields": [{"field": "source_ids", "reason": "包含空项"}]},
                )
            normalized.append(item.strip())
    elif not all_pending and source_ids is not None:
        raise AppError(
            ErrorCode.VALIDATION,
            "source_ids 与 all_pending 至少提供一个",
            {"fields": [{"field": "source_ids", "reason": "必填（与 all_pending 二选一）"}]},
        )
    else:
        # 空请求体视为全部待编译：前端「立即编译」的默认语义。
        normalized = _pending_source_ids(store)

    if not normalized:
        raise AppError(ErrorCode.VALIDATION, "没有待编译的素材")
    job = await CompileEngine(queue=job_queue).start_compile(store.vault, normalized)
    return {"job_id": job.id, "queued_sources": len(normalized)}


@router.get("/compile/current")
async def current_job() -> dict:
    """围观页快照；无任何编译任务时返回 idle（API-025）。"""

    compile_jobs = _compile_jobs()
    active = [job for job in compile_jobs if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}]
    if active:
        return _snapshot(active[-1])
    if compile_jobs:
        return _snapshot(compile_jobs[-1])
    return {"job_id": None, "status": "idle"}


@router.get("/compile/jobs/{job_id}")
async def job_detail(job_id: str) -> dict:
    """历史任务详情查询（API-026）。"""

    job = job_queue.get(job_id)
    if job is None:
        raise AppError(ErrorCode.NOT_FOUND, "任务不存在", {"job_id": job_id})
    return _snapshot(job)


@router.get("/changes")
async def get_changes(job_id: str | None = Query(None)) -> dict:
    """变更清单；缺省取最近一次编译任务（API-027）。"""

    if job_id is None:
        compile_jobs = _compile_jobs()
        if not compile_jobs:
            raise AppError(ErrorCode.NOT_FOUND, "还没有编译任务")
        job = compile_jobs[-1]
    else:
        job = job_queue.get(job_id)
        if job is None:
            raise AppError(ErrorCode.NOT_FOUND, "任务不存在", {"job_id": job_id})

    store = _vault()
    manifest_path = store.vault / ".llmwiki" / "compile" / f"{job.id}.json"
    manifest: dict[str, Any] = {"items": [], "failed_sources": []}
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text("utf-8"))
            if isinstance(loaded, dict):
                manifest = loaded
        except (OSError, json.JSONDecodeError):
            # 清单损坏时保留任务状态，条目按空处理，不阻塞页面。
            pass

    items: list[dict[str, Any]] = []
    for item in manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", ""))
        items.append(
            {
                "name": str(item.get("name", "")),
                "title": str(item.get("title", "")),
                "change_type": action if action in _MANIFEST_KINDS else "updated",
                "zone": str(item.get("zone", "")),
                "zone_before": item.get("zone_before"),
                "has_diff": bool(item.get("has_diff", False)),
            }
        )

    failed_sources = [
        {
            "id": str(item.get("id", "")),
            "title": str(item.get("title", "")),
            "reason": str(item.get("reason", "")),
        }
        for item in manifest.get("failed_sources", [])
        if isinstance(item, dict)
    ]

    return {
        "job_id": job.id,
        "status": job.status.value,
        "started_at": _iso(job.started_at),
        "finished_at": _iso(job.finished_at),
        "cost": {"currency": "USD", "total": read_job_cost(store.vault, job.id)},
        "items": items,
        "failed_sources": failed_sources,
    }
