"""B 站视频采集。

策略（从快到慢，逐级兜底）：
  1. b23.tv 短链还原为 av/BV 号
  2. 官方 web 接口 view/detail —— 一次请求拿到标题、简介、UP 主、分区、标签、热评
  3. 播放器接口取 CC/AI 字幕 → 视频文稿
  4. yt-dlp 兜底再试一次字幕
没有字幕时（未登录常见），仍然会保留标题 + 简介 + 标签 + 热评，并在文档里标注提示。
"""

from __future__ import annotations

import re
from typing import Any

from .. import config
from ..textutil import join_nonempty
from .common import (
    IngestError,
    IngestResult,
    fetch_json,
    fetch_text,
    human_duration,
    timestamp_to_date,
    vtt_to_text,
    ytdlp_subtitles,
)

BVID_RE = re.compile(r"BV[0-9A-Za-z]{10}")
AV_RE = re.compile(r"av(\d+)", re.IGNORECASE)
B23_RE = re.compile(r"https?://b23\.tv/[0-9A-Za-z]+")
URL_RE = re.compile(r"https?://[^\s\u4e00-\u9fff，。！？、；：""''（）【】]+")

API_HEADERS_REFERER = "https://www.bilibili.com/"


def matches(text: str) -> bool:
    return bool(BVID_RE.search(text) or B23_RE.search(text) or "bilibili.com" in text or "b23.tv" in text)


def _resolve_target(text: str) -> tuple[str, str]:
    """返回 (bvid 或 aid 参数, 规范化的原始链接)。"""
    bvid_match = BVID_RE.search(text)
    if bvid_match:
        bvid = bvid_match.group(0)
        return f"bvid={bvid}", f"https://www.bilibili.com/video/{bvid}"

    short_match = B23_RE.search(text)
    if short_match:
        try:
            final_url, _ = fetch_text(short_match.group(0), mobile=True)
        except Exception as exc:  # noqa: BLE001
            raise IngestError(f"短链还原失败：{exc}") from exc
        bvid_match = BVID_RE.search(final_url)
        if bvid_match:
            bvid = bvid_match.group(0)
            return f"bvid={bvid}", f"https://www.bilibili.com/video/{bvid}"
        av_match = AV_RE.search(final_url)
        if av_match:
            return f"aid={av_match.group(1)}", final_url
        raise IngestError("无法从短链中解析出视频号")

    url_match = URL_RE.search(text)
    if url_match:
        url = url_match.group(0)
        av_match = AV_RE.search(url)
        if av_match:
            return f"aid={av_match.group(1)}", url
    raise IngestError("没有识别到有效的 B 站视频链接")


def _api(path: str, cookie: str = "") -> dict[str, Any]:
    data = fetch_json(
        f"https://api.bilibili.com{path}",
        cookie=cookie,
        referer=API_HEADERS_REFERER,
    )
    if not isinstance(data, dict):
        raise IngestError("B 站接口返回异常")
    if data.get("code") not in (0, None):
        raise IngestError(f"B 站接口报错：{data.get('message') or data.get('code')}")
    return data.get("data") or {}


def _fetch_subtitle(bvid: str, cid: int, cookie: str) -> str:
    """取 CC / AI 字幕正文。未登录时接口常返回空列表。"""
    for endpoint in ("/x/player/v2", "/x/player/wbi/v2"):
        try:
            data = _api(f"{endpoint}?bvid={bvid}&cid={cid}", cookie=cookie)
        except Exception:
            continue
        subtitles = (((data.get("subtitle") or {}).get("subtitles")) or [])
        if not subtitles:
            continue
        # 优先中文
        subtitles.sort(key=lambda s: (0 if str(s.get("lan", "")).startswith("zh") else 1, len(str(s.get("lan", "")))))
        for item in subtitles:
            url = item.get("subtitle_url") or ""
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith("http"):
                continue
            try:
                payload = fetch_json(url, cookie=cookie, referer=API_HEADERS_REFERER)
            except Exception:
                continue
            body = payload.get("body") if isinstance(payload, dict) else None
            if not body:
                continue
            text = vtt_to_text("\n".join(str(seg.get("content", "")) for seg in body))
            if text:
                return text
    return ""


def extract(url_or_text: str, share_text: str = "") -> IngestResult:
    cookie = config.load_config()["fetch"].get("bilibili_cookie", "")
    query, canonical_url = _resolve_target(url_or_text)
    warnings: list[str] = []

    detail: dict[str, Any] = {}
    try:
        detail = _api(f"/x/web-interface/view/detail?{query}", cookie=cookie)
    except IngestError:
        detail = {}
    if not detail:
        detail = _api(f"/x/web-interface/view?{query}", cookie=cookie)

    view = detail.get("View") or detail
    if not view.get("title"):
        raise IngestError("没有取到视频信息，可能视频已删除或需要登录")

    bvid = view.get("bvid") or ""
    aid = view.get("aid")
    title = str(view.get("title", "")).strip()
    desc = str(view.get("desc", "")).strip()
    owner = (view.get("owner") or {}).get("name", "")
    owner_mid = (view.get("owner") or {}).get("mid")
    pubdate = timestamp_to_date(view.get("pubdate"))
    duration = human_duration(view.get("duration"))
    cover = view.get("pic") or ""
    if cover.startswith("//"):
        cover = "https:" + cover
    tname = view.get("tname") or ""
    stat = view.get("stat") or {}
    pages = view.get("pages") or []
    cid = view.get("cid") or (pages[0].get("cid") if pages else None)

    # 标签
    tags: list[str] = []
    for tag in (detail.get("Tags") or []):
        name = str(tag.get("tag_name", "")).strip()
        if name and name not in tags:
            tags.append(name)
    if tname and tname not in tags:
        tags.insert(0, tname)

    # 字幕
    transcript = ""
    if bvid and cid:
        transcript = _fetch_subtitle(bvid, int(cid), cookie)
    if not transcript and config.load_config()["fetch"].get("enable_ytdlp", True):
        transcript = ytdlp_subtitles(canonical_url)
    if not transcript:
        warnings.append("未获取到字幕文稿：B 站字幕接口需要登录态（可在 config.yaml 填 bilibili_cookie 后重试）")

    # 热评
    comments: list[str] = []
    replies = ((detail.get("Reply") or {}).get("replies")) or []
    for reply in replies[:15]:
        message = ((reply.get("content") or {}).get("message") or "").strip()
        uname = ((reply.get("member") or {}).get("uname") or "").strip()
        like = reply.get("like") or 0
        if message:
            # 评论里可能带换行，压成空格才能保持「一条一行」
            flat = re.sub(r"\s+", " ", message)
            comments.append(f"- **{uname}**（{like} 赞）：{flat}")

    # 分P
    parts: list[str] = []
    if len(pages) > 1:
        for page in pages:
            parts.append(f"- P{page.get('page')} {page.get('part')}（{human_duration(page.get('duration'))}）")

    # 合集
    season_lines: list[str] = []
    season = view.get("ugc_season") or {}
    if season.get("title"):
        season_lines.append(f"合集：{season['title']}")
        for section in season.get("sections") or []:
            for episode in (section.get("episodes") or [])[:50]:
                arc = episode.get("arc") or {}
                if arc.get("title"):
                    season_lines.append(f"- {arc['title']}")

    stat_line = " · ".join(
        filter(
            None,
            [
                f"播放 {stat.get('view', 0):,}" if stat.get("view") is not None else "",
                f"点赞 {stat.get('like', 0):,}" if stat.get("like") is not None else "",
                f"弹幕 {stat.get('danmaku', 0):,}" if stat.get("danmaku") is not None else "",
            ],
        )
    )

    header = f"> 来源：B 站 · UP 主 **{owner}**"
    if duration:
        header += f" · 时长 {duration}"
    if pubdate:
        header += f" · 发布于 {pubdate}"
    if stat_line:
        header += f" · {stat_line}"
    header += f"\n> 原链接：{canonical_url}"

    body = join_nonempty(
        [
            f"# {title}",
            header,
            "## 视频简介\n" + desc if desc else "",
            "## 分P目录\n" + "\n".join(parts) if parts else "",
            "## 合集\n" + "\n".join(season_lines) if season_lines else "",
            "## 视频文稿（字幕）\n" + transcript if transcript else "",
            "## 热门评论\n" + "\n".join(comments) if comments else "",
        ]
    )

    if share_text.strip() and share_text.strip() not in body:
        body += f"\n\n## 原始分享文本\n{share_text.strip()}"

    raw_meta = {
        "bvid": bvid,
        "aid": aid,
        "cid": cid,
        "owner_mid": owner_mid,
        "duration": duration,
        "tname": tname,
        "stat": stat,
        "has_transcript": bool(transcript),
        "page_count": len(pages),
    }

    return IngestResult(
        title=title,
        source_type="bilibili",
        content_md=body,
        source_url=canonical_url,
        author=owner,
        published_at=pubdate,
        cover_url=cover,
        raw_meta=raw_meta,
        tags=tags[:12],
        warnings=warnings,
    )
