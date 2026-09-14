"""采集路由：识别输入类型 → 抽取内容 → 归一化为 Markdown。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import vault
from ..textutil import clean_markdown, join_nonempty, slugify
from . import bilibili, docfile, douyin, webpage
from .common import IngestError, IngestResult

__all__ = [
    "IngestError",
    "IngestResult",
    "SOURCE_LABELS",
    "ingest_file",
    "ingest_one",
    "save_to_raw",
    "split_inputs",
]

SOURCE_LABELS = {
    "douyin": "抖音",
    "bilibili": "B 站",
    "web": "网页",
    "doc": "文档",
    "pdf": "PDF",
    "markdown": "Markdown",
    "text": "文本",
}

_URL_LINE_RE = re.compile(r"https?://\S+")


# --------------------------------------------------------------------------- #
# 输入切分
# --------------------------------------------------------------------------- #

def split_inputs(text: str) -> list[str]:
    """把一大段粘贴内容拆成一条条待收录的输入。

    支持两种粘贴习惯：
      * 一行一个链接 / 一段文字
      * 抖音那种「文案 + 短链」混在一行的分享文本（整行保留，链接单独识别）
    """
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []

    lines = [line.strip() for line in text.split("\n")]
    items: list[str] = []
    buffer: list[str] = []

    for line in lines:
        if not line:
            if buffer:
                items.append("\n".join(buffer))
                buffer = []
            continue
        urls = _URL_LINE_RE.findall(line)
        if urls and len(line) <= max(len(u) for u in urls) + 40:
            # 这一行基本就是链接本身
            if buffer:
                items.append("\n".join(buffer))
                buffer = []
            for url in urls:
                items.append(url.rstrip("，。、；：）】"))
        elif urls:
            # 分享文案 + 链接混排：整行作为一条，交给采集器解析
            if buffer:
                items.append("\n".join(buffer))
                buffer = []
            items.append(line)
        else:
            buffer.append(line)

    if buffer:
        items.append("\n".join(buffer))

    # 去重（保留顺序）
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def detect_type(text: str) -> str:
    if douyin.matches(text):
        return "douyin"
    if bilibili.matches(text):
        return "bilibili"
    if webpage.matches(text):
        return "web"
    return "text"


# --------------------------------------------------------------------------- #
# 文本 / 链接
# --------------------------------------------------------------------------- #

def _from_plain_text(text: str) -> IngestResult:
    body = clean_markdown(text)
    heading = re.search(r"^\s{0,3}#\s+(.+)$", body, re.M)
    if heading:
        title = heading.group(1).strip()
    else:
        first_line = next((line.strip() for line in body.split("\n") if line.strip()), "随手记")
        # 优先取第一句，太长的整段文本不要整句当标题
        sentence = re.split(r"[。！？!?；;\n]", first_line)[0].strip()
        sentence = re.sub(r"^[#>\-*\s]+", "", sentence)
        title = (sentence[:42] or first_line[:42] or "随手记").strip()
        body = f"# {title}\n\n{body}"
    return IngestResult(
        title=title,
        source_type="text",
        content_md=body,
        raw_meta={"origin": "manual"},
    )


def ingest_one(text: str, tags: list[str] | None = None) -> IngestResult:
    """收录一条输入（链接或纯文本）。"""
    kind = detect_type(text)
    if kind == "douyin":
        result = douyin.extract(text, share_text=text)
    elif kind == "bilibili":
        result = bilibili.extract(text, share_text=text)
    elif kind == "web":
        result = webpage.extract(text, share_text=text)
    else:
        result = _from_plain_text(text)

    if tags:
        result.tags = list(dict.fromkeys([*tags, *result.tags]))
    result.raw_meta.setdefault("detected_type", kind)
    return result


# --------------------------------------------------------------------------- #
# 文件
# --------------------------------------------------------------------------- #

def ingest_file(path: Path, filename: str = "", tags: list[str] | None = None) -> IngestResult:
    result = docfile.extract(path, original_name=filename or path.name)
    if tags:
        result.tags = list(dict.fromkeys([*tags, *result.tags]))
    return result


# --------------------------------------------------------------------------- #
# 落盘到 raw/
# --------------------------------------------------------------------------- #

def save_to_raw(result: IngestResult) -> str:
    """把采集结果写入 raw/，返回相对路径。"""
    name = slugify(result.title, result.source_type or "source")
    meta: dict[str, Any] = {
        "title": result.title,
        "source_type": result.source_type,
        "source_url": result.source_url,
        "author": result.author,
        "published_at": result.published_at,
        "cover_url": result.cover_url,
        "tags": result.tags,
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta.update({k: v for k, v in (result.raw_meta or {}).items() if k not in meta and v not in (None, "", [], {})})
    return vault.save_raw(name, result.content_md, meta)


def ingest_to_raw(text: str, tags: list[str] | None = None) -> dict[str, Any]:
    """收录 + 落盘，返回 {result, raw_path}。"""
    result = ingest_one(text, tags=tags)
    raw_path = save_to_raw(result)
    return {"result": result, "raw_path": raw_path}


def ingest_file_to_raw(path: Path, filename: str = "", tags: list[str] | None = None) -> dict[str, Any]:
    result = ingest_file(path, filename=filename, tags=tags)
    raw_path = save_to_raw(result)
    return {"result": result, "raw_path": raw_path}


def preview(result: IngestResult, raw_path: str) -> dict[str, Any]:
    return {
        "title": result.title,
        "source_type": result.source_type,
        "source_type_label": SOURCE_LABELS.get(result.source_type, result.source_type),
        "source_url": result.source_url,
        "author": result.author,
        "raw_path": raw_path,
        "chars": len(result.content_md),
        "tags": result.tags[:10],
        "warnings": result.warnings,
        "excerpt": join_nonempty([result.content_md[:600]]),
    }
