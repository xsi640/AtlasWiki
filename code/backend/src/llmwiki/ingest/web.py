"""网页素材解析与导入（TASK-008）。"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import trafilatura

from llmwiki.errors import AppError, ErrorCode
from llmwiki.schema import MaterialKind, MaterialStatus
from llmwiki.workspace.store import WikiStore


def _unique_tags(tags: list[str] | None) -> list[str]:
    return list(dict.fromkeys(t.strip() for t in tags or [] if t.strip()))


def _validate_url(url: str) -> None:
    if not url.strip():
        raise AppError(
            ErrorCode.VALIDATION,
            "URL 不能为空",
            {"fields": [{"field": "url", "reason": "必填"}]},
        )
    if not re.match(r"^https?://", url.strip()):
        raise AppError(
            ErrorCode.VALIDATION,
            "URL 必须以 http:// 或 https:// 开头",
            {"fields": [{"field": "url", "reason": "必须是 http/https 链接"}]},
        )


def _extract_content(html: str, url: str) -> tuple[str, str | None]:
    """用 trafilatura 提取正文，返回 (text, author)。"""
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True)
    if not text or not text.strip():
        raise ValueError("正文提取结果为空")
    # trafilatura 可以提取作者（bare_extraction 返回 Document 对象）
    try:
        meta = trafilatura.bare_extraction(html, url=url)
        author = getattr(meta, "author", None) if meta else None
    except Exception:
        author = None
    return text.strip(), author


def _import_web_sync(
    url: str,
    *,
    title: str | None,
    tags: list[str] | None,
    fetched_html: str | None = None,
) -> dict[str, Any]:
    """同步导入逻辑（可注入 fetched_html 供测试使用）。"""
    _validate_url(url)

    if fetched_html is None:
        resp = httpx.get(url.strip(), timeout=30, follow_redirects=True)
        resp.raise_for_status()
        fetched_html = resp.text

    content, author = _extract_content(fetched_html, url)
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    material_id = content_hash[:12]

    store = WikiStore.from_config()
    store.initialize()

    # 去重：检查同 id 素材是否已存在
    existing_path = Path("raw") / f"{material_id}.md"
    if store.resolve_path(existing_path).exists():
        existing = store.read_markdown(existing_path)
        raise AppError(
            ErrorCode.DUPLICATE_SOURCE,
            "素材已存在（内容重复）",
            {
                "existing": {
                    "id": existing.metadata.get("id"),
                    "title": existing.metadata.get("title"),
                }
            },
        )

    now = datetime.now(UTC).isoformat()
    if not title:
        try:
            doc = trafilatura.bare_extraction(fetched_html, url=url)
            resolved_title = getattr(doc, "title", None) or url  # type: ignore[union-attr]
        except Exception:
            resolved_title = url
    else:
        resolved_title = title

    metadata = {
        "id": material_id,
        "title": str(resolved_title),
        "kind": MaterialKind.WEB.value,
        "source_url": url,
        "author": author,
        "status": MaterialStatus.NORMAL.value,
        "tags": _unique_tags(tags),
        "raw_meta": {"extractor": "trafilatura"},
    }
    store.write_markdown(existing_path, metadata, content, update_timestamp=True)

    return {
        **metadata,
        "content": content,
        "content_editable": False,
        "created_at": now,
        "updated_at": now,
        "failure_reason": None,
    }


async def fetch_web(
    url: str,
    *,
    title: str | None = None,
    tags: list[str] | None = None,
    fetched_html: str | None = None,
) -> dict:
    """抓取并导入网页素材。"""
    return await asyncio.to_thread(
        _import_web_sync, url, title=title, tags=tags, fetched_html=fetched_html
    )
