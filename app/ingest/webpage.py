"""通用网页采集：trafilatura 主抽取 + 轻量正文提取兜底。"""

from __future__ import annotations

import re
from typing import Any

from ..textutil import clean_markdown, join_nonempty, readability_extract, strip_page_boilerplate
from .common import IngestError, IngestResult, fetch_text, meta_content

URL_RE = re.compile(r"https?://[^\s\u4e00-\u9fff，。！？、；：""''（）【】]+")


def extract_url(text: str) -> str:
    match = URL_RE.search(text or "")
    if not match:
        raise IngestError("没有识别到网址")
    return match.group(1) if match.lastindex else match.group(0)


def matches(text: str) -> bool:
    return bool(URL_RE.search(text or ""))


def _trafilatura_extract(html: str, url: str) -> tuple[str, dict[str, Any]]:
    try:
        import trafilatura
        from trafilatura.settings import use_config
    except Exception:
        return "", {}

    settings = use_config()
    settings.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
    try:
        markdown = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_links=True,
            include_images=False,
            include_formatting=True,
            include_tables=True,
            favor_recall=True,
            settings=settings,
        )
    except Exception:
        markdown = ""

    meta: dict[str, Any] = {}
    try:
        doc = trafilatura.extract_metadata(html, default_url=url)
        if doc:
            meta = {
                "title": (doc.title or "").strip(),
                "author": (doc.author or "").strip(),
                "date": (doc.date or "").strip(),
                "sitename": (doc.sitename or "").strip(),
                "description": (doc.description or "").strip(),
                "image": (doc.image or "").strip(),
            }
    except Exception:
        meta = {}
    return (markdown or "").strip(), meta


def extract(url_or_text: str, share_text: str = "") -> IngestResult:
    url = extract_url(url_or_text)
    warnings: list[str] = []

    try:
        final_url, html = fetch_text(url)
    except Exception as exc:  # noqa: BLE001
        raise IngestError(f"抓取网页失败：{exc}") from exc

    if not html.strip():
        raise IngestError("网页内容为空")

    markdown, meta = _trafilatura_extract(html, final_url)
    if len(markdown) < 200:
        fallback_title, fallback_md = readability_extract(html)
        if len(fallback_md) > len(markdown):
            markdown = fallback_md
            warnings.append("主抽取器效果不佳，已改用轻量正文提取")
        if fallback_title and not meta.get("title"):
            meta["title"] = fallback_title

    if not markdown.strip():
        raise IngestError("没能从网页里提取出正文（可能是需要登录或纯 JS 渲染的页面）")

    title = (meta.get("title") or "").strip() or meta_content(html, "og:title", "twitter:title")
    if not title:
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
        title = re.sub(r"\s+", " ", match.group(1)).strip() if match else ""
    title = title or final_url

    author = (meta.get("author") or "").strip()
    published = (meta.get("date") or "").strip()
    sitename = (meta.get("sitename") or "").strip()
    cover = (meta.get("image") or "").strip() or meta_content(html, "og:image")

    header_bits = [f"来源：{sitename or '网页'}"]
    if author:
        header_bits.append(f"作者 {author}")
    if published:
        header_bits.append(f"日期 {published}")
    header = "> " + " · ".join(header_bits) + f"\n> 原链接：{final_url}"

    # 先剥掉页面尾部的解析器诊断块（维基百科 NewPP limit report 之类），
    # 否则它们会被当作正文，污染关键词与摘要。
    content = join_nonempty([f"# {title}", header, clean_markdown(strip_page_boilerplate(markdown))])

    return IngestResult(
        title=title,
        source_type="web",
        content_md=content,
        source_url=final_url,
        author=author,
        published_at=published,
        cover_url=cover,
        raw_meta={"sitename": sitename, "description": meta.get("description", ""), "bytes": len(html)},
        warnings=warnings,
    )
