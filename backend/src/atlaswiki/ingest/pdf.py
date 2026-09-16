"""PDF 素材解析与导入（TASK-009）。"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.schema import MaterialKind, MaterialStatus
from atlaswiki.workspace.store import WikiStore, atomic_write_bytes


def _clean_metadata_value(value: Any) -> str | None:
    """清理 PDF 元数据；空白值统一视为缺失。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _reader_metadata(reader: PdfReader) -> dict[str, str | None]:
    """读取标题与作者；元数据损坏不阻断正文解析。"""

    metadata: dict[str, Any]
    try:
        metadata = dict(reader.metadata or {})
    except Exception:
        metadata = {}
    return {
        "title": _clean_metadata_value(metadata.get("/Title")),
        "author": _clean_metadata_value(metadata.get("/Author")),
    }


def _extract_pdf(source_path: Path) -> tuple[str, dict[str, str | None], int]:
    """同步解析 PDF，返回正文、元信息与页数。"""

    if not source_path.is_file():
        raise ValueError("PDF 文件不存在")

    data = source_path.read_bytes()
    if not data:
        raise ValueError("PDF 文件为空")

    try:
        reader = PdfReader(source_path)
        if reader.is_encrypted:
            raise ValueError("PDF 已加密")
        metadata = _reader_metadata(reader)
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ValueError(f"PDF 无法解析: {exc}") from exc

    if not page_texts:
        raise ValueError("PDF 没有页面")

    text = "\n\n".join(page_text.strip() for page_text in page_texts if page_text.strip())
    if not text.strip():
        raise ValueError("PDF 没有可提取的文本层（可能是扫描版）")
    return text, metadata, len(page_texts)


def _unique_tags(tags: list[str] | None) -> list[str]:
    """去除空标签并保持首次出现顺序。"""

    return list(dict.fromkeys(tag.strip() for tag in tags or [] if tag.strip()))


def _existing_material(
    store: WikiStore,
    relative_path: Path,
    content_hash: str,
) -> AppError | None:
    """同一内容重复导入时，按 API 契约生成冲突异常。"""

    if not store.resolve_path(relative_path).exists():
        return None
    document = store.read_markdown(relative_path)
    return AppError(
        ErrorCode.DUPLICATE_SOURCE,
        "PDF 素材已存在",
        {
            "content_hash": content_hash,
            "existing": {
                "id": document.metadata.get("id"),
                "title": document.metadata.get("title"),
            },
        },
    )


def _failed_document(
    metadata: dict[str, Any],
    content: str,
    *,
    asset_relative_path: Path,
    reason: str,
) -> dict[str, Any]:
    """生成失败素材的响应载荷。"""

    return {
        **metadata,
        "content": content,
        "content_editable": False,
        "failure_reason": reason,
        "asset_path": str(asset_relative_path),
    }


def _import_pdf_sync(
    file_path: Path,
    *,
    title: str | None,
    tags: list[str] | None,
) -> dict[str, Any]:
    """执行导入；解析失败时会保留原件并落盘 failed 素材。"""

    source_path = Path(file_path).expanduser()
    store = WikiStore.from_config()
    store.initialize()

    try:
        data = source_path.read_bytes()
    except OSError as exc:
        raise AppError(ErrorCode.PARSE_FAILED, "PDF 文件不可读", {"path": str(source_path)}) from exc

    content_hash = hashlib.sha256(data).hexdigest()
    material_id = content_hash[:12]
    asset_relative_path = Path("raw") / "assets" / f"{material_id}.pdf"
    material_relative_path = Path("raw") / f"{material_id}.md"

    duplicate = _existing_material(store, material_relative_path, content_hash)
    if duplicate is not None:
        raise duplicate

    # 先保留用户上传的原件，后续任何解析错误都不能破坏它。
    asset_path = store.resolve_path(asset_relative_path)
    atomic_write_bytes(asset_path, data)

    common_metadata: dict[str, Any] = {
        "id": material_id,
        "kind": MaterialKind.PDF.value,
        "source_url": None,
        "tags": _unique_tags(tags),
        "asset_path": str(asset_relative_path),
    }

    try:
        content, pdf_metadata, page_count = _extract_pdf(asset_path)
    except Exception as exc:
        reason = str(exc)
        metadata = {
            **common_metadata,
            "title": title or source_path.stem or "未命名 PDF",
            "author": None,
            "published_at": None,
            "note": None,
            "status": MaterialStatus.FAILED.value,
            "raw_meta": {"extractor": "pypdf", "page_count": None},
        }
        store.write_markdown(
            material_relative_path,
            metadata,
            "",
            update_timestamp=True,
        )
        raise AppError(
            ErrorCode.PARSE_FAILED,
            reason,
            _failed_document(metadata, "", asset_relative_path=asset_relative_path, reason=reason),
        ) from exc

    resolved_title = title or pdf_metadata["title"] or source_path.stem or "未命名 PDF"
    metadata = {
        **common_metadata,
        "title": resolved_title,
        "author": pdf_metadata["author"],
        "published_at": None,
        "note": None,
        "status": MaterialStatus.NORMAL.value,
        "raw_meta": {
            "extractor": "pypdf",
            "page_count": page_count,
        },
    }
    store.write_markdown(material_relative_path, metadata, content, update_timestamp=True)
    return {
        **metadata,
        "content": content,
        "content_editable": False,
        "failure_reason": None,
        "asset_path": str(asset_relative_path),
    }


async def import_pdf(
    file_path: Path,
    *,
    title: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """导入并解析 PDF，原件保存到 vault 的 ``raw/assets``。"""

    return await asyncio.to_thread(
        _import_pdf_sync,
        file_path,
        title=title,
        tags=tags,
    )
