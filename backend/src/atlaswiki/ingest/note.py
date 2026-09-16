"""手写笔记素材导入（TASK-010）。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.schema import MaterialKind, MaterialStatus
from atlaswiki.workspace.store import WikiStore as MarkdownStore
from atlaswiki.workspace.store import normalize_page_name


def _utc_now() -> str:
    """返回素材文件使用的 ISO8601 UTC 时间。"""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _validated_inputs(title: str, content: str, tags: list[str] | None) -> tuple[str, str, list[str]]:
    """校验字段并返回用于落盘的标题与标签。"""

    field_errors: dict[str, str] = {}
    normalized_title = title.strip()
    if not normalized_title:
        field_errors["title"] = "标题不能为空"

    if not content.strip():
        field_errors["content"] = "正文不能为空"

    normalized_tags = [tag.strip() for tag in (tags or [])]
    if any(not tag for tag in normalized_tags):
        field_errors["tags"] = "标签不能为空"

    if field_errors:
        raise AppError(
            ErrorCode.VALIDATION,
            "手写笔记校验失败",
            {"fields": field_errors},
        )

    page_name = normalize_page_name(normalized_title)
    if not page_name:
        field_errors["title"] = "标题规范化后不能为空"
        raise AppError(
            ErrorCode.VALIDATION,
            "手写笔记校验失败",
            {"fields": field_errors},
        )
    return page_name, content, normalized_tags


def _import_note_sync(title: str, content: str, tags: list[str] | None) -> dict[str, Any]:
    """在工作线程中执行磁盘写入，避免阻塞事件循环。"""

    normalized_title, note_content, normalized_tags = _validated_inputs(title, content, tags)
    store = MarkdownStore.from_config()
    store.initialize()

    source_id = uuid.uuid4().hex[:12]
    timestamp = _utc_now()
    relative_path = f"raw/{normalized_title}-{source_id}.md"
    metadata: dict[str, Any] = {
        "id": source_id,
        "title": normalized_title,
        "kind": MaterialKind.NOTE.value,
        "source_url": None,
        "status": MaterialStatus.NORMAL.value,
        "tags": normalized_tags,
        "content_editable": True,
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    store.write_markdown(relative_path, metadata, note_content)
    return {
        **metadata,
        "path": relative_path,
        "content": note_content,
    }


async def import_note(title: str, content: str, *, tags: list[str] | None = None) -> dict:
    """导入一篇手写笔记，并返回素材元数据。"""

    return await asyncio.to_thread(_import_note_sync, title, content, tags)
