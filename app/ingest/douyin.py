"""抖音采集。

抖音没有公开稳定的内容接口，采用多级兜底：
  1. yt-dlp 取元数据（标题/文案/作者/封面）—— 命中率最高
  2. 还原 v.douyin.com 短链 → 解析分享页里的 RENDER_DATA / _ROUTER_DATA JSON
  3. 解析 og:title / og:description meta
  4. 最差情况：只把用户粘贴的分享文本本身存下来，保证不丢信息
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from ..textutil import join_nonempty
from .common import (
    IngestError,
    IngestResult,
    deep_find,
    fetch_text,
    meta_content,
    timestamp_to_date,
    ytdlp_metadata,
)

URL_RE = re.compile(r"https?://[^\s\u4e00-\u9fff，。！？、；：""''（）【】]+")
AWEME_ID_RE = re.compile(r"(?:video|note|share/video)/(\d{6,})")
SHORT_HOSTS = ("v.douyin.com", "www.iesdouyin.com/share", "iesdouyin.com/share")


def matches(text: str) -> bool:
    lowered = text.lower()
    return (
        "douyin.com" in lowered
        or "iesdouyin.com" in lowered
        or "抖音" in text
        and URL_RE.search(text) is not None
    )


def _extract_url(text: str) -> str:
    match = URL_RE.search(text)
    if not match:
        raise IngestError("没有识别到抖音链接")
    return match.group(0).rstrip("，。、；：）】")


def _aweme_id_from_url(url: str) -> str:
    match = AWEME_ID_RE.search(url)
    return match.group(1) if match else ""


def _expand(url: str) -> str:
    """还原短链，拿到最终地址。"""
    try:
        final_url, _ = fetch_text(url, mobile=True)
        return final_url
    except Exception:
        return url


def _parse_embedded_json(html: str) -> dict[str, Any]:
    """从分享页里挖出内嵌的 JSON 数据。"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for script_id in ("RENDER_DATA", "__NEXT_DATA__", "RENDER_DATA_SSR"):
        tag = soup.find("script", id=script_id)
        if not tag or not tag.string:
            continue
        raw = tag.string.strip()
        for candidate in (raw, urllib.parse.unquote(raw)):
            try:
                payload = json.loads(candidate)
            except Exception:
                continue
            found = deep_find(
                payload,
                lambda node: "aweme_id" in node and ("desc" in node or "author" in node),
            )
            if found:
                return found
    return {}


def _from_html(url: str) -> tuple[dict[str, Any], str]:
    """抓分享页，返回 (aweme 详情, 原始 html)。"""
    candidates = [url]
    aweme_id = _aweme_id_from_url(url)
    if aweme_id:
        candidates.append(f"https://www.iesdouyin.com/share/video/{aweme_id}/")
    html = ""
    for candidate in candidates:
        try:
            _, html = fetch_text(candidate, mobile=True)
        except Exception:
            continue
        detail = _parse_embedded_json(html)
        if detail:
            return detail, html
    return {}, html


def extract(url_or_text: str, share_text: str = "") -> IngestResult:
    from .. import config

    url = _extract_url(url_or_text)
    if any(host in url for host in SHORT_HOSTS) or "v.douyin.com" in url:
        url = _expand(url)

    warnings: list[str] = []
    aweme: dict[str, Any] = {}
    html = ""

    # 1) yt-dlp
    if config.load_config()["fetch"].get("enable_ytdlp", True):
        meta = ytdlp_metadata(url)
    else:
        meta = {}
    if meta:
        aweme = {
            "desc": meta.get("description") or meta.get("title") or "",
            "author": {"nickname": meta.get("uploader") or meta.get("channel") or ""},
            "create_time": meta.get("timestamp"),
            "statistics": {
                "digg_count": meta.get("like_count"),
                "comment_count": meta.get("comment_count"),
                "play_count": meta.get("view_count"),
            },
            "video": {"cover": {"url_list": [meta.get("thumbnail")] if meta.get("thumbnail") else []}},
            "_title": meta.get("title") or "",
            "_duration": meta.get("duration"),
        }

    # 2) 分享页
    if not aweme:
        aweme, html = _from_html(url)

    # 3) meta 兜底
    if not aweme and html:
        og_title = meta_content(html, "og:title", "twitter:title") or ""
        og_desc = meta_content(html, "og:description", "description") or ""
        if og_title or og_desc:
            aweme = {"_title": og_title, "desc": og_desc}

    if not aweme:
        warnings.append("抖音页面未能解析出结构化信息，已仅保存分享文本")

    desc = str(aweme.get("desc") or aweme.get("_title") or "").strip()
    author = ""
    author_node = aweme.get("author")
    if isinstance(author_node, dict):
        author = str(author_node.get("nickname") or author_node.get("unique_id") or "").strip()
    published = timestamp_to_date(aweme.get("create_time"))

    cover = ""
    video_node = aweme.get("video") or {}
    if isinstance(video_node, dict):
        cover_node = video_node.get("cover") or {}
        if isinstance(cover_node, dict):
            urls = cover_node.get("url_list") or []
            if urls:
                cover = str(urls[0])
    if not cover:
        cover = meta_content(html, "og:image") if html else ""

    stats = aweme.get("statistics") or {}
    stat_line = ""
    if isinstance(stats, dict):
        stat_line = " · ".join(
            filter(
                None,
                [
                    f"点赞 {stats['digg_count']:,}" if stats.get("digg_count") else "",
                    f"评论 {stats['comment_count']:,}" if stats.get("comment_count") else "",
                    f"收藏 {stats['collect_count']:,}" if stats.get("collect_count") else "",
                ],
            )
        )

    hashtags: list[str] = []
    for item in aweme.get("text_extra") or []:
        name = str(item.get("hashtag_name") or "").strip()
        if name:
            hashtags.append(f"#{name}")

    # 标题取文案首句，太长则截断
    title = desc.split("\n")[0][:80].strip() or "抖音作品"
    title = re.sub(r"#\S+", "", title).strip() or title

    header = f"> 来源：抖音 · 作者 **{author or '未知'}**"
    if published:
        header += f" · 发布于 {published}"
    if stat_line:
        header += f" · {stat_line}"
    header += f"\n> 原链接：{url}"

    body = join_nonempty(
        [
            f"# {title}",
            header,
            "## 作品文案\n" + desc if desc else "",
            "## 话题标签\n" + " ".join(hashtags) if hashtags else "",
            (
                "## 原始分享文本\n" + share_text.strip()
                if share_text.strip() and share_text.strip() not in (desc or "")
                else ""
            ),
        ]
    )

    warnings.append("抖音无公开字幕接口，本条保存的是作品文案与元信息，不是视频逐字稿")

    raw_meta = {
        "aweme_id": str(aweme.get("aweme_id") or _aweme_id_from_url(url) or ""),
        "author_id": (aweme.get("author") or {}).get("unique_id") if isinstance(aweme.get("author"), dict) else "",
        "statistics": stats if isinstance(stats, dict) else {},
        "hashtags": hashtags,
        "duration": aweme.get("_duration"),
    }

    return IngestResult(
        title=title,
        source_type="douyin",
        content_md=body,
        source_url=url,
        author=author,
        published_at=published,
        cover_url=cover,
        raw_meta=raw_meta,
        tags=hashtags[:10],
        warnings=warnings,
    )
