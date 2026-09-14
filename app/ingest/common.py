"""采集层公共工具：HTTP 客户端、统一返回结构、VTT 字幕解析、yt-dlp 辅助。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .. import config

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)


class IngestError(RuntimeError):
    """采集失败，message 会直接展示给用户。"""


@dataclass
class IngestResult:
    title: str
    source_type: str
    content_md: str
    source_url: str = ""
    author: str = ""
    published_at: str = ""
    cover_url: str = ""
    raw_meta: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "source_type": self.source_type,
            "content_md": self.content_md,
            "source_url": self.source_url,
            "author": self.author,
            "published_at": self.published_at,
            "cover_url": self.cover_url,
            "raw_meta": {**self.raw_meta, "warnings": self.warnings},
            "tags": self.tags,
        }


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def build_client(mobile: bool = False, extra_headers: dict | None = None, cookie: str = "") -> httpx.Client:
    cfg = config.load_config()["fetch"]
    headers = {
        "User-Agent": MOBILE_UA if mobile else cfg["user_agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    if cookie:
        headers["Cookie"] = cookie
    if extra_headers:
        headers.update(extra_headers)
    kwargs: dict[str, Any] = {
        "headers": headers,
        "timeout": float(cfg["timeout"]),
        "follow_redirects": True,
    }
    if cfg.get("proxy"):
        kwargs["proxy"] = cfg["proxy"]
    return httpx.Client(**kwargs)


def fetch_text(url: str, *, mobile: bool = False, cookie: str = "", referer: str = "") -> tuple[str, str]:
    """抓取网页，返回 (最终 URL, HTML 文本)。"""
    cfg = config.load_config()["fetch"]
    headers = {"Referer": referer} if referer else None
    with build_client(mobile=mobile, extra_headers=headers, cookie=cookie) as client:
        response = client.get(url)
        response.raise_for_status()
        if len(response.content) > int(cfg["max_bytes"]):
            raise IngestError("页面体积过大，已跳过")
        return str(response.url), response.text


def fetch_json(url: str, *, mobile: bool = False, cookie: str = "", referer: str = "") -> Any:
    headers = {"Referer": referer} if referer else None
    with build_client(mobile=mobile, extra_headers=headers, cookie=cookie) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


# --------------------------------------------------------------------------- #
# yt-dlp（可选增强：拿到更完整的元数据与字幕）
# --------------------------------------------------------------------------- #

def ytdlp_available() -> bool:
    return shutil.which("yt-dlp") is not None or _ytdlp_module_available()


def _ytdlp_module_available() -> bool:
    try:
        import yt_dlp  # noqa: F401
        return True
    except Exception:
        return False


def _ytdlp_cmd() -> list[str]:
    binary = shutil.which("yt-dlp")
    if binary:
        return [binary]
    return [str(Path(__import__("sys").executable)), "-m", "yt_dlp"]


def ytdlp_metadata(url: str, timeout: int | None = None) -> dict[str, Any]:
    """用 yt-dlp 取元数据（不下载视频）。失败返回空 dict。"""
    if timeout is None:
        timeout = config.ytdlp_timeout()
    if not ytdlp_available():
        return {}
    cmd = [
        *_ytdlp_cmd(),
        "--dump-single-json",
        "--no-warnings",
        "--no-playlist",
        "--skip-download",
        url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return {}
    if proc.returncode != 0 or not proc.stdout.strip():
        return {}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {}


def ytdlp_subtitles(url: str, langs: str = "zh-Hans,zh-CN,zh,ai-zh", timeout: int | None = None) -> str:
    """尝试下载字幕并转成纯文本。失败返回空串。"""
    if timeout is None:
        # 抓字幕要下载并解析 VTT，比抓元数据慢，给它两倍预算
        timeout = config.ytdlp_timeout() * 2
    if not ytdlp_available():
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            *_ytdlp_cmd(),
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs", langs,
            "--sub-format", "vtt",
            "--no-warnings",
            "--no-playlist",
            "-o", "%(id)s.%(ext)s",
            "--paths", f"temp:{tmp}",
            url,
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except Exception:
            return ""
        files = sorted(Path(tmp).glob("*.vtt"))
        if not files:
            return ""
        # 优先中文
        files.sort(key=lambda p: (0 if "zh" in p.name.lower() else 1, len(p.name)))
        return vtt_to_text(files[0].read_text(encoding="utf-8", errors="ignore"))


_VTT_TIME_RE = re.compile(r"^\d{1,2}:\d{2}:\d{2}\.\d{3}\s+-->")
_VTT_TAG_RE = re.compile(r"<[^>]+>")


def vtt_to_text(vtt: str) -> str:
    """把 WebVTT 字幕转成连续文本，去掉重复的滚动字幕行。"""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE")):
            continue
        if _VTT_TIME_RE.match(line) or line.isdigit():
            continue
        line = _VTT_TAG_RE.sub("", line).strip()
        if not line:
            continue
        if lines and (line == lines[-1] or line in lines[-1] or lines[-1] in line):
            # 滚动字幕会重复上一句，保留更长的那条
            if len(line) > len(lines[-1]):
                lines[-1] = line
            continue
        lines.append(line)

    merged: list[str] = []
    for line in lines:
        if merged and not re.search(r"[。！？.!?]$", merged[-1]) and len(merged[-1]) < 40:
            merged[-1] = merged[-1] + line
        else:
            merged.append(line)
    text = "".join(merged) if _is_cjk(merged) else " ".join(merged)
    return re.sub(r"\s{2,}", " ", text).strip()


def _is_cjk(lines: list[str]) -> bool:
    sample = "".join(lines)[:200]
    if not sample:
        return False
    cjk = len(re.findall(r"[\u4e00-\u9fff]", sample))
    return cjk / max(1, len(sample)) > 0.3


def human_duration(seconds: int | float | None) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def timestamp_to_date(ts: int | float | None) -> str:
    if not ts:
        return ""
    from datetime import datetime
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        return ""


def deep_find(obj: Any, predicate, max_depth: int = 8) -> Any:
    """在嵌套 JSON 里递归查找第一个满足条件的节点。"""
    if max_depth < 0:
        return None
    if isinstance(obj, dict):
        if predicate(obj):
            return obj
        for value in obj.values():
            found = deep_find(value, predicate, max_depth - 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = deep_find(item, predicate, max_depth - 1)
            if found is not None:
                return found
    return None


def meta_content(html: str, *names: str) -> str:
    """从 HTML 的 meta 标签里取内容。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""
