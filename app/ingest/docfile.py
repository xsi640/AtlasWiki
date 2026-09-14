"""本地文件采集：docx / doc / rtf / pdf / md / txt / html。

.doc 这类老格式走 macOS 自带的 textutil（无需额外依赖），
Linux 上会尝试 antiword，都不可用时给出明确提示。
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..textutil import clean_markdown, html_to_markdown, join_nonempty, strip_markdown
from .common import IngestError, IngestResult

DOCX_EXT = {".docx", ".dotx"}
DOC_EXT = {".doc", ".dot"}
RTF_EXT = {".rtf"}
PDF_EXT = {".pdf"}
TEXT_EXT = {".md", ".markdown", ".mdx", ".txt", ".text", ".log"}
HTML_EXT = {".html", ".htm"}

SUPPORTED = DOCX_EXT | DOC_EXT | RTF_EXT | PDF_EXT | TEXT_EXT | HTML_EXT

SOURCE_TYPE_BY_EXT = {
    **{ext: "doc" for ext in DOCX_EXT | DOC_EXT | RTF_EXT},
    **{ext: "pdf" for ext in PDF_EXT},
    **{ext: "markdown" for ext in {".md", ".markdown", ".mdx"}},
    **{ext: "text" for ext in {".txt", ".text", ".log"}},
    **{ext: "web" for ext in HTML_EXT},
}


def is_supported(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED


# --------------------------------------------------------------------------- #
# docx
# --------------------------------------------------------------------------- #

def _docx_to_markdown(path: Path) -> tuple[str, str, dict]:
    from docx import Document  # type: ignore
    from docx.table import Table  # type: ignore
    from docx.text.paragraph import Paragraph  # type: ignore

    document = Document(str(path))
    parts: list[str] = []
    headings: list[str] = []
    image_count = 0
    table_count = 0

    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = para.text.strip()
            style = (para.style.name or "") if para.style is not None else ""
            if para._p.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
                image_count += 1
            if not text:
                continue
            level_match = re.match(r"Heading (\d)", style)
            if level_match:
                level = min(int(level_match.group(1)), 6)
                parts.append(f"\n{'#' * level} {text}\n")
                headings.append(text)
            elif style.startswith("Title"):
                parts.append(f"\n# {text}\n")
                headings.append(text)
            elif style.startswith("List"):
                parts.append(f"- {text}")
            else:
                parts.append(text)
        elif tag == "tbl":
            table_count += 1
            table = Table(child, document)
            rows = []
            for row in table.rows:
                cells = [re.sub(r"\s+", " ", cell.text).strip() for cell in row.cells]
                rows.append(cells)
            if not rows:
                continue
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
            for row in rows[1:]:
                lines.append("| " + " | ".join(row) + " |")
            parts.append("\n" + "\n".join(lines) + "\n")

    core = document.core_properties
    title = (core.title or "").strip() or (headings[0] if headings else "")
    author = (core.author or "").strip()
    created = core.created.strftime("%Y-%m-%d") if core.created else ""

    markdown = clean_markdown("\n".join(parts))
    meta = {
        "paragraphs": len(document.paragraphs),
        "tables": table_count,
        "images": image_count,
        "doc_title": (core.title or "").strip(),
    }
    return title, markdown, {"author": author, "published_at": created, "meta": meta}


# --------------------------------------------------------------------------- #
# 老格式 .doc / .rtf —— 优先用系统工具
# --------------------------------------------------------------------------- #

def _via_textutil(path: Path) -> str:
    textutil = shutil.which("textutil")
    if not textutil:
        return ""
    try:
        proc = subprocess.run(
            [textutil, "-convert", "txt", "-stdout", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _via_antiword(path: Path) -> str:
    antiword = shutil.which("antiword")
    if not antiword:
        return ""
    try:
        proc = subprocess.run([antiword, str(path)], capture_output=True, text=True, timeout=60)
    except Exception:
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def _via_libreoffice(path: Path) -> str:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "txt:Text", "--outdir", tmp, str(path)],
                capture_output=True,
                text=True,
                timeout=180,
            )
        except Exception:
            return ""
        for candidate in Path(tmp).glob("*.txt"):
            return candidate.read_text(encoding="utf-8", errors="ignore")
    return ""


def _legacy_doc_text(path: Path) -> tuple[str, str]:
    """返回 (文本, 使用的工具名)。"""
    for name, func in (
        ("textutil", _via_textutil),
        ("antiword", _via_antiword),
        ("libreoffice", _via_libreoffice),
    ):
        text = func(path)
        if text and text.strip():
            return text, name
    hint = (
        "未找到可用的 .doc 转换工具。"
        if platform.system() == "Darwin"
        else "未找到可用的 .doc 转换工具，请安装 antiword 或 libreoffice 后重试。"
    )
    raise IngestError(f"无法读取旧版 Word 文档（{path.name}）。{hint}")


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

def _pdf_meta(reader: Any) -> dict[str, str]:
    """PDF 文档属性里的作者与创建日期。

    pypdf 会把 /CreationDate 解析成 datetime；畸形 PDF 上属性访问本身也可能抛错，
    所以整体包一层。
    """
    try:
        meta = reader.metadata
    except Exception:
        return {}
    if not meta:
        return {}

    def read(name: str) -> str:
        try:
            value = getattr(meta, name, None)
        except Exception:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        return str(value or "").strip()

    return {"title": read("title"), "author": read("author"), "created": read("creation_date")}


def _pdf_to_text(path: Path) -> tuple[str, int, dict[str, str]]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise IngestError("未安装 pypdf，无法读取 PDF") from exc

    reader = PdfReader(str(path))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = re.sub(r"[ \t]+", " ", text).strip()
        if text:
            pages.append(f"### 第 {index} 页\n{text}")
    return "\n\n".join(pages), len(reader.pages), _pdf_meta(reader)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

def extract(path: Path, original_name: str = "") -> IngestResult:
    path = Path(path)
    name = original_name or path.name
    ext = Path(name).suffix.lower()
    warnings: list[str] = []
    title = Path(name).stem
    author = published = ""
    raw_meta: dict = {"filename": name, "size": path.stat().st_size if path.exists() else 0}

    if ext in DOCX_EXT:
        doc_title, markdown, extra = _docx_to_markdown(path)
        title = doc_title or title
        author = extra.get("author", "")
        published = extra.get("published_at", "")
        raw_meta.update(extra.get("meta", {}))
    elif ext in DOC_EXT or ext in RTF_EXT:
        text, tool = _legacy_doc_text(path)
        markdown = clean_markdown(text)
        raw_meta["converter"] = tool
    elif ext in PDF_EXT:
        text, page_count, pdf_meta = _pdf_to_text(path)
        markdown = clean_markdown(text)
        raw_meta["pages"] = page_count
        # 作者与日期取自文档属性。标题**不覆盖**文件名：PDF 的 /Title 通常由生成
        # 工具写入（常见「Microsoft Word - draft3.docx」这类），不如用户自己起的
        # 文件名可靠；原值仍记进 raw_meta 供参考。
        author = pdf_meta.get("author", "")
        published = pdf_meta.get("created", "")
        raw_meta["pdf_title"] = pdf_meta.get("title", "")
        if len(strip_markdown(markdown)) < 200 and page_count > 0:
            warnings.append("该 PDF 可能是扫描件，未能提取到文字（需要 OCR）")
    elif ext in HTML_EXT:
        html = path.read_text(encoding="utf-8", errors="ignore")
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        markdown = clean_markdown(html_to_markdown(soup.body or soup))
    elif ext in TEXT_EXT:
        markdown = path.read_text(encoding="utf-8", errors="ignore")
        markdown = clean_markdown(markdown)
    else:
        raise IngestError(f"暂不支持的文件类型：{ext or '未知'}")

    if not markdown.strip():
        raise IngestError(f"文件 {name} 中未提取到任何文本")

    # Markdown 文件如果首行是 H1，用它当标题
    first_heading = re.search(r"^\s{0,3}#\s+(.+)$", markdown, re.M)
    if first_heading and ext in TEXT_EXT | {".md", ".markdown", ".mdx"}:
        title = first_heading.group(1).strip()

    header = f"> 来源：本地文件 `{name}`"
    if author:
        header += f" · 作者 {author}"
    if published:
        header += f" · 日期 {published}"

    content = join_nonempty([f"# {title}", header, markdown])

    return IngestResult(
        title=title,
        source_type=SOURCE_TYPE_BY_EXT.get(ext, "doc"),
        content_md=content,
        source_url="",
        author=author,
        published_at=published,
        raw_meta=raw_meta,
        warnings=warnings,
    )
