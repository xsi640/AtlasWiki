"""问答接口（API-028 ~ API-032）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from atlaswiki.config import config_store
from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.jobs import job_queue
from atlaswiki.schema import PageType, SourceType, normalize_page_name
from atlaswiki.workspace.store import PageDraft, WikiStore

from ..ask import AskEngine, QueryStore

router = APIRouter(prefix="/api", tags=["ask"])


class AskRequest(BaseModel):
    """POST /api/ask 请求。"""

    question: str


class SaveAsPageRequest(BaseModel):
    """回填请求；全部字段可选。"""

    title: str | None = None
    zone: str | None = None


def _vault() -> WikiStore:
    settings = config_store.load()
    if not settings.vault_path:
        raise AppError(ErrorCode.VALIDATION, "尚未配置 vault 路径", {"fields": ["vault_path"]})
    store = WikiStore(Path(settings.vault_path).expanduser().resolve())
    if not store.initialized:
        raise AppError(ErrorCode.NOT_FOUND, "vault 不存在或尚未初始化")
    return store


def _parse_body(model_type: type[BaseModel], body: Any) -> BaseModel:
    if body is None:
        if model_type is SaveAsPageRequest:
            return SaveAsPageRequest()
        raise AppError(ErrorCode.VALIDATION, "请求体不能为空")
    if not isinstance(body, dict):
        raise AppError(ErrorCode.VALIDATION, "请求体必须是 JSON 对象")
    try:
        return model_type.model_validate(body)
    except Exception as exc:
        fields = [
            {"field": ".".join(str(part) for part in error["loc"]), "reason": error["msg"]}
            for error in exc.errors()
        ]
        raise AppError(ErrorCode.VALIDATION, "请求参数无效", {"fields": fields}) from exc


def _serialize_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id", ""),
        "question": record.get("question", ""),
        "sufficient": record.get("sufficient", False),
        "pages_considered": record.get("pages_considered", 0),
        "cost": record.get("cost", {"currency": "USD", "total": 0}),
        "created_at": record.get("created_at", ""),
        "saved_page": record.get("saved_page"),
    }


def _default_title(question: str) -> str:
    title = re.sub(r"[?？!！。：:;；,，\s]+", " ", question).strip()
    words = title.split()
    return (" ".join(words[:8]) or "问答分析").strip()


@router.post("/ask")
async def ask(body: dict | None = None) -> dict:
    """同步返回完整问答结果；执行过程进入全局串行写入队列。"""

    request = _parse_body(AskRequest, body)
    if not request.question.strip():
        raise AppError(
            ErrorCode.VALIDATION,
            "问题不能为空",
            {"fields": [{"field": "question", "reason": "必填"}]},
        )
    if not config_store.load().llm.api_key.strip():
        raise AppError(ErrorCode.LLM_NOT_CONFIGURED, "LLM API key 未配置")
    store = _vault()
    engine = AskEngine()
    queue = job_queue

    async def run(job) -> None:
        await engine.ask(job, store.vault, request.question)

    job = await queue.submit("ask", run)
    await queue.join()
    if job.status.value == "failed":
        raise AppError(
            ErrorCode.LLM_NOT_CONFIGURED
            if "API key" in (job.error or "")
            else ErrorCode.VALIDATION,
            job.error or "问答失败",
        )

    queries = QueryStore(store.vault)
    records = await queries.list_all()
    record = next((item for item in reversed(records) if item.get("job_id") == job.id), None)
    if record is None:
        raise AppError(ErrorCode.NOT_FOUND, "问答结果不存在", {"job_id": job.id})
    return record


@router.post("/ask/{query_id}/save-as-page")
async def save_as_page(query_id: str, body: dict | None = None) -> dict:
    """把答案回填为 analysis 页面；重复调用返回既有页面。"""

    request = _parse_body(SaveAsPageRequest, body)
    store = _vault()
    queries = QueryStore(store.vault)
    record = await queries.get(query_id)
    if record is None:
        raise AppError(ErrorCode.NOT_FOUND, "问答记录不存在", {"query_id": query_id})
    if record.get("saved_page"):
        saved = record["saved_page"]
        return {
            "page": {"name": saved.get("name"), "title": saved.get("title")},
            "job_id": record.get("job_id", query_id),
        }
    if not str(record.get("answer", "")).strip():
        raise AppError(ErrorCode.VALIDATION, "答案为空，无法回填")

    queue = job_queue

    async def run(job) -> None:
        title = (request.title or _default_title(str(record.get("question", "")))).strip()
        desired = normalize_page_name(title)
        base = desired or "问答分析"
        used = set(store.list_page_names())
        candidate = base
        serial = 2
        while candidate in used:
            candidate = f"{base}-{serial}"
            serial += 1
        zone = (request.zone or str(record.get("zone", "")) or "分析").strip()
        page = store.write_page(
            PageDraft(
                name=candidate,
                title=title,
                page_type=PageType.ANALYSIS,
                source_type=SourceType.QUERY_GENERATED.value,
                zone=zone,
                content=str(record.get("answer", "")).strip(),
                origin_source=query_id,
                metadata={"query_id": query_id},
            )
        )

        def updater(item: dict[str, Any]) -> dict[str, Any]:
            item["saved_page"] = {"name": page.name, "title": page.title}
            return item

        await queries.update(query_id, updater)
        await queue.update_progress(job, progress=1.0, done=1, detail=page.name)

    job = await queue.submit("ask-save", run)
    await queue.join()
    if job.status.value == "failed":
        raise AppError(ErrorCode.VALIDATION, job.error or "答案回填失败")
    updated = await queries.get(query_id)
    if not updated or not updated.get("saved_page"):
        raise AppError(ErrorCode.NOT_FOUND, "答案回填结果不存在")
    page_info = updated["saved_page"]
    return {
        "page": {"name": page_info.get("name"), "title": page_info.get("title")},
        "job_id": job.id,
    }


@router.get("/queries")
async def list_queries(page: int = 1, size: int = 50) -> dict:
    """返回问答历史；新记录排在前面。"""

    if page < 1 or size < 1:
        raise AppError(ErrorCode.VALIDATION, "分页参数必须大于 0")
    store = _vault()
    items = await QueryStore(store.vault).list_all()
    start = (page - 1) * size
    selected = items[-start - size : len(items) - start] if start < len(items) else []
    selected = list(reversed(selected))
    return {"items": [_serialize_summary(item) for item in selected], "total": len(items)}


@router.get("/queries/{query_id}")
async def get_query(query_id: str) -> dict:
    store = _vault()
    record = await QueryStore(store.vault).get(query_id)
    if record is None:
        raise AppError(ErrorCode.NOT_FOUND, "问答记录不存在", {"query_id": query_id})
    return record


@router.delete("/queries/{query_id}")
async def delete_query(query_id: str) -> dict:
    store = _vault()
    deleted = await QueryStore(store.vault).delete(query_id)
    if not deleted:
        raise AppError(ErrorCode.NOT_FOUND, "问答记录不存在", {"query_id": query_id})
    return {"ok": True, "id": query_id}
