"""素材接口（API-014 ~ API-023）。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from llmwiki.compile import CompileEngine
from llmwiki.config import config_store
from llmwiki.errors import AppError, ErrorCode
from llmwiki.ingest.note import import_note as ingest_note
from llmwiki.ingest.pdf import import_pdf as ingest_pdf
from llmwiki.ingest.service import source_service
from llmwiki.ingest.web import fetch_web as ingest_web
from llmwiki.jobs import job_queue
from llmwiki.workspace.store import WikiStore

router = APIRouter(prefix="/api/sources", tags=["sources"])

# 上传原件的大小保护；超限必须给出明确错误而不是让请求挂死。
_MAX_UPLOAD_BYTES = 100 * 1024 * 1024


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


def _parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_tags(tags: str | list[str] | None) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(tag).strip() for tag in tags if str(tag).strip()]
    return [tag.strip() for tag in tags.split(",") if tag.strip()]


def _require_field(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AppError(
            ErrorCode.VALIDATION,
            "请求参数无效",
            {"fields": [{"field": key, "reason": "必填"}]},
        )
    return value.strip()


async def _finalize_import(result: dict, *, compile_after: bool) -> dict:
    """导入成功后补齐 SourceDetail 形状，并按需排队编译。"""

    store = _vault()
    detail = await source_service.get_source(store.vault, str(result["id"]))
    if compile_after:
        job = await CompileEngine(queue=job_queue).start_compile(store.vault, [str(result["id"])])
        detail["job_id"] = job.id
    return detail


@router.get("")
async def list_sources(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> dict:
    """素材列表；status 支持逗号分隔多值筛选。"""

    statuses = [item.strip() for item in status.split(",") if item.strip()] if status else None
    return await source_service.list_sources(_vault().vault, status=statuses, page=page, size=size)


@router.post("/web")
@router.post("/url")  # api-design.md 中的原始路径，保留为别名。
async def import_web(body: dict | None = None) -> dict:
    """导入网页素材（API-015）。"""

    if not isinstance(body, dict):
        raise AppError(ErrorCode.VALIDATION, "请求体必须是 JSON 对象")
    url = _require_field(body, "url")
    title = body.get("title")
    if title is not None and not isinstance(title, str):
        raise AppError(
            ErrorCode.VALIDATION,
            "请求参数无效",
            {"fields": [{"field": "title", "reason": "必须是字符串"}]},
        )
    tags = _parse_tags(body.get("tags"))
    compile_after = _parse_bool(body.get("compile"))
    result = await ingest_web(url, title=title, tags=tags)
    return await _finalize_import(result, compile_after=compile_after)


@router.post("/note")
async def import_note(body: dict | None = None) -> dict:
    """新建手写笔记素材（API-016）。"""

    if not isinstance(body, dict):
        raise AppError(ErrorCode.VALIDATION, "请求体必须是 JSON 对象")
    # 类型在 API 层拦截；空值交给服务层一次性报出全部字段错误。
    for key in ("title", "content"):
        if not isinstance(body.get(key), str):
            raise AppError(
                ErrorCode.VALIDATION,
                "请求参数无效",
                {"fields": [{"field": key, "reason": "必填"}]},
            )
    tags = _parse_tags(body.get("tags"))
    compile_after = _parse_bool(body.get("compile"))
    result = await ingest_note(body["title"], body["content"], tags=tags)
    return await _finalize_import(result, compile_after=compile_after)


@router.post("/pdf")
@router.post("/upload")  # api-design.md 中的原始路径，保留为别名。
async def import_pdf(
    file: Annotated[UploadFile, File(...)],
    title: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    compile: Annotated[str, Form()] = "false",
) -> dict:
    """上传 PDF 素材（API-017）。"""

    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    with tempfile.NamedTemporaryFile(prefix="llmwiki-upload-", suffix=suffix, delete=False) as handle:
        size = 0
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > _MAX_UPLOAD_BYTES:
                handle.close()
                Path(handle.name).unlink(missing_ok=True)
                raise AppError(
                    ErrorCode.VALIDATION,
                    f"上传文件超过大小上限（{_MAX_UPLOAD_BYTES // (1024 * 1024)} MB）",
                    {"fields": [{"field": "file", "reason": "文件过大"}]},
                )
            handle.write(chunk)
        temp_path = Path(handle.name)

    try:
        result = await ingest_pdf(
            temp_path,
            title=(title.strip() if title and title.strip() else None),
            tags=_parse_tags(tags),
        )
    finally:
        temp_path.unlink(missing_ok=True)
    return await _finalize_import(result, compile_after=_parse_bool(compile))


@router.get("/{source_id}/asset", response_model=None)
async def get_asset(source_id: str, download: bool = Query(False)) -> Any:
    """返回素材原件；download=1 直接回文件流，否则返回路径（API-023）。"""

    store = _vault()
    detail = await source_service.get_source(store.vault, source_id)
    asset_relative = detail.get("asset_path")
    if not asset_relative:
        raise AppError(ErrorCode.NOT_FOUND, "该素材没有原件", {"source_id": source_id})
    asset_absolute = store.resolve_path(asset_relative)
    if not asset_absolute.is_file():
        raise AppError(ErrorCode.NOT_FOUND, "原件文件缺失", {"path": str(asset_relative)})
    if download:
        return FileResponse(asset_absolute, filename=asset_absolute.name)
    return {"path": str(asset_absolute), "opened": False}


@router.post("/{source_id}/restore")
async def restore_source(source_id: str) -> dict:
    """从已删除恢复素材（API-021）。"""

    return await source_service.restore_source(_vault().vault, source_id)


@router.post("/{source_id}/recompile")
async def recompile_source(source_id: str) -> dict:
    """对单个素材重跑编译（API-022）。"""

    store = _vault()
    await source_service.get_source(store.vault, source_id)  # 不存在时先返回 404
    job = await CompileEngine(queue=job_queue).start_compile(store.vault, [source_id])
    return {"job_id": job.id, "queued_sources": 1}


@router.get("/{source_id}")
async def get_source(source_id: str) -> dict:
    """素材详情与派生页列表（API-018）。"""

    return await source_service.get_source(_vault().vault, source_id)


@router.patch("/{source_id}")
async def update_source(source_id: str, body: dict | None = None) -> dict:
    """部分更新素材；note 可改正文，其余只改元数据（API-019）。"""

    if not isinstance(body, dict) or not body:
        raise AppError(ErrorCode.VALIDATION, "请求体不能为空")
    return await source_service.update_source(_vault().vault, source_id, body)


@router.delete("/{source_id}")
async def delete_source(source_id: str) -> dict:
    """软删除素材（API-020）。"""

    return await source_service.delete_source(_vault().vault, source_id)
