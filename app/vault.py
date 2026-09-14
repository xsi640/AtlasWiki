"""Vault 文件层：raw/ 原始素材 + wiki/ LLM 维护的页面。

设计原则（对齐 Karpathy 的 LLM Wiki）：
  * 文件是唯一真相来源，没有任何数据库
  * raw/ 只读，wiki/ 由 LLM 全权编写
  * 页面之间用 [[双链]] 连接，反向链接从链接图现算
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from . import config
from .textutil import clean_markdown, clip, slugify

KIND_DIRS = ("sources", "entities", "concepts", "analyses")
ROOT_PAGES = ("index.md", "overview.md", "conventions.md")
LOG_FILE = "log.md"

KIND_LABELS = {
    "sources": "素材",
    "entities": "实体",
    "concepts": "概念",
    "analyses": "分析",
    "root": "总览",
}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")
_MDLINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+\.md)(?:#[^)]*)?\)")
_H1_RE = re.compile(r"^\s{0,3}#\s+(.+?)\s*$", re.M)


class VaultError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# 数据模型
# --------------------------------------------------------------------------- #

@dataclass
class Page:
    rel_path: str
    kind: str
    slug: str
    title: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    links: list[str] = field(default_factory=list)
    backlinks: list[str] = field(default_factory=list)
    size: int = 0
    updated_at: str = ""

    @property
    def path(self) -> Path:
        return config.wiki_dir() / self.rel_path

    def to_dict(self, with_body: bool = True) -> dict[str, Any]:
        data = {
            "path": self.rel_path,
            "kind": self.kind,
            "kind_label": KIND_LABELS.get(self.kind, self.kind),
            "slug": self.slug,
            "title": self.title,
            "tags": self.frontmatter.get("tags") or [],
            "summary": self.frontmatter.get("summary") or "",
            "sources": self.frontmatter.get("sources") or [],
            "links": self.links,
            "backlinks": self.backlinks,
            "size": self.size,
            "created_at": str(self.frontmatter.get("created") or ""),
            "updated_at": self.updated_at,
            "is_root": self.kind == "root",
        }
        if with_body:
            data["body"] = self.body
        return data


# --------------------------------------------------------------------------- #
# frontmatter
# --------------------------------------------------------------------------- #

def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    text = text or ""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, text[match.end() :]


def render_page(frontmatter: dict[str, Any], body: str) -> str:
    meta = {k: v for k, v in (frontmatter or {}).items() if v not in (None, "", [], {})}
    if not meta:
        return (body or "").strip() + "\n"
    head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{head}\n---\n\n{(body or '').strip()}\n"


def extract_title(body: str, fallback: str) -> str:
    match = _H1_RE.search(body or "")
    return match.group(1).strip() if match else fallback


# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #

def _safe_path(rel_path: str) -> Path:
    rel = (rel_path or "").strip().lstrip("/")
    rel = rel.replace("\\", "/")
    if not rel.endswith(".md"):
        rel += ".md"
    if ".." in Path(rel).parts:
        raise VaultError(f"非法路径：{rel_path}")
    target = (config.wiki_dir() / rel).resolve()
    root = config.wiki_dir().resolve()
    if root not in target.parents and target != root:
        raise VaultError(f"路径越界：{rel_path}")
    return target


def normalize_rel(rel_path: str) -> str:
    rel = (rel_path or "").strip().lstrip("/").replace("\\", "/")
    if not rel.endswith(".md"):
        rel += ".md"
    return rel


def kind_of(rel_path: str) -> str:
    rel = normalize_rel(rel_path)
    head = rel.split("/")[0]
    return head if head in KIND_DIRS else "root"


def slug_of(rel_path: str) -> str:
    return Path(normalize_rel(rel_path)).stem


# --------------------------------------------------------------------------- #
# 链接
# --------------------------------------------------------------------------- #

def extract_links(body: str) -> list[str]:
    """抽取 [[双链]] 与指向本地 .md 的 Markdown 链接。"""
    links: list[str] = []
    for raw in _WIKILINK_RE.findall(body or ""):
        target = raw.split("|")[0].split("#")[0].strip()
        if target:
            links.append(target)
    for _, target in _MDLINK_RE.findall(body or ""):
        target = target.strip()
        if target.startswith(("http://", "https://")):
            continue
        links.append(target)
    seen: set[str] = set()
    ordered: list[str] = []
    for link in links:
        key = link.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(link)
    return ordered


def build_link_map(pages: Iterable[Page]) -> dict[str, str]:
    """建立 标题/slug/路径 → rel_path 的解析表。"""
    mapping: dict[str, str] = {}
    for page in pages:
        for key in (page.title, page.slug, page.rel_path, Path(page.rel_path).stem):
            if key:
                mapping.setdefault(key.strip().lower(), page.rel_path)
    return mapping


def resolve_link(target: str, link_map: dict[str, str]) -> str | None:
    key = (target or "").strip().lstrip("/").lower()
    if not key:
        return None
    if key in link_map:
        return link_map[key]
    if key.endswith(".md") and key[:-3] in link_map:
        return link_map[key[:-3]]
    if not key.endswith(".md") and f"{key}.md" in link_map:
        return link_map[f"{key}.md"]
    return None


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #

def _read_page_file(path: Path) -> Page:
    text = path.read_text(encoding="utf-8", errors="ignore")
    meta, body = parse_frontmatter(text)
    rel = str(path.relative_to(config.wiki_dir())).replace("\\", "/")
    kind = kind_of(rel)
    slug = slug_of(rel)
    title = str(meta.get("title") or "").strip() or extract_title(body, slug)
    stat = path.stat()
    return Page(
        rel_path=rel,
        kind=kind,
        slug=slug,
        title=title,
        frontmatter=meta,
        body=body.strip(),
        links=extract_links(body),
        size=stat.st_size,
        updated_at=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
    )


def list_pages(include_log: bool = False, with_backlinks: bool = True) -> list[Page]:
    root = config.wiki_dir()
    if not root.exists():
        return []
    pages: list[Page] = []
    for path in sorted(root.rglob("*.md")):
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel.startswith("."):
            continue
        if not include_log and rel == LOG_FILE:
            continue
        try:
            pages.append(_read_page_file(path))
        except Exception:
            continue

    if with_backlinks:
        link_map = build_link_map(pages)
        incoming: dict[str, list[str]] = {page.rel_path: [] for page in pages}
        for page in pages:
            for link in page.links:
                target = resolve_link(link, link_map)
                if target and target != page.rel_path and page.rel_path not in incoming.get(target, []):
                    incoming.setdefault(target, []).append(page.rel_path)
        for page in pages:
            page.backlinks = incoming.get(page.rel_path, [])
    return pages


def page_index() -> dict[str, Page]:
    return {page.rel_path: page for page in list_pages(with_backlinks=False)}


def read_page(rel_path: str) -> Page | None:
    path = _safe_path(rel_path)
    if not path.exists():
        return None
    return _read_page_file(path)


def page_exists(rel_path: str) -> bool:
    try:
        return _safe_path(rel_path).exists()
    except VaultError:
        return False


# --------------------------------------------------------------------------- #
# 写入
# --------------------------------------------------------------------------- #

def write_page(
    rel_path: str,
    body: str,
    *,
    title: str | None = None,
    frontmatter: dict[str, Any] | None = None,
    merge_frontmatter: bool = True,
) -> Page:
    path = _safe_path(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing_meta: dict[str, Any] = {}
    existing_created = ""
    if path.exists():
        old_meta, _ = parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
        existing_meta = old_meta
        existing_created = str(old_meta.get("created") or "")

    body = clean_markdown(body)
    now = datetime.now().strftime("%Y-%m-%d")
    meta: dict[str, Any] = {}
    if merge_frontmatter:
        meta.update(existing_meta)
    if frontmatter:
        meta.update({k: v for k, v in frontmatter.items() if v is not None})
    meta.setdefault("created", existing_created or now)
    meta["updated"] = now
    meta["title"] = title or str(meta.get("title") or "").strip() or extract_title(body, slug_of(rel_path))

    path.write_text(render_page(meta, body), encoding="utf-8")
    return _read_page_file(path)


def append_page(rel_path: str, extra: str, *, title: str | None = None) -> Page:
    """追加内容到已有页面末尾（不存在则新建）。"""
    path = _safe_path(rel_path)
    if path.exists():
        page = _read_page_file(path)
        body = page.body + "\n\n" + clean_markdown(extra)
        return write_page(rel_path, body, title=title or page.title, frontmatter=page.frontmatter)
    return write_page(rel_path, extra, title=title)


def edit_page(rel_path: str, old: str, new: str, replace_all: bool = False) -> tuple[bool, str]:
    path = _safe_path(rel_path)
    if not path.exists():
        return False, f"页面不存在：{rel_path}"
    text = path.read_text(encoding="utf-8", errors="ignore")
    if old not in text:
        return False, "未找到要替换的内容（old_string 必须与文件中的内容完全一致）"
    updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    path.write_text(updated, encoding="utf-8")
    return True, f"已更新 {rel_path}"


def delete_page(rel_path: str) -> bool:
    path = _safe_path(rel_path)
    if not path.exists():
        return False
    trash = config.vault_dir() / ".trash"
    trash.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    shutil.move(str(path), str(trash / f"{stamp}-{path.name}"))
    return True


# --------------------------------------------------------------------------- #
# index / log / overview
# --------------------------------------------------------------------------- #

def read_index() -> str:
    path = config.wiki_dir() / "index.md"
    if not path.exists():
        return ""
    _, body = parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
    return body.strip()


def write_index(content: str) -> None:
    write_page("index.md", content, title="索引", frontmatter={"type": "index"})


def rebuild_index() -> str:
    """确定性重建 index.md（LLM 也可以调用它，或自己手写更精炼的版本）。"""
    pages = list_pages(with_backlinks=True)
    grouped: dict[str, list[Page]] = {kind: [] for kind in KIND_DIRS}
    roots: list[Page] = []
    for page in pages:
        if page.kind == "root":
            if page.rel_path not in ("index.md",):
                roots.append(page)
            continue
        grouped.setdefault(page.kind, []).append(page)

    lines: list[str] = ["# 索引", ""]
    total = sum(len(v) for v in grouped.values())
    lines.append(f"共 {total} 个页面。")
    lines.append("")
    if roots:
        lines.append("## 总览")
        for page in sorted(roots, key=lambda p: p.title):
            lines.append(f"- [[{page.title}]] — {clip(page.frontmatter.get('summary') or '', 60)}")
        lines.append("")
    for kind in KIND_DIRS:
        items = sorted(grouped.get(kind, []), key=lambda p: p.title)
        if not items:
            continue
        lines.append(f"## {KIND_LABELS.get(kind, kind)}（{len(items)}）")
        for page in items:
            summary = str(page.frontmatter.get("summary") or "").strip()
            source_count = len(page.frontmatter.get("sources") or [])
            suffix = f" · 引用 {source_count} 个素材" if source_count else ""
            lines.append(f"- [[{page.title}]] — {summary}{suffix}" if summary else f"- [[{page.title}]]{suffix}")
        lines.append("")
    content = "\n".join(lines).strip() + "\n"
    write_index(content)
    return content


def append_log(kind: str, message: str) -> None:
    path = config.wiki_dir() / LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = (message or "").strip().splitlines() or [""]
    entry = [f"## [{stamp}] {kind} | {lines[0]}"]
    entry.extend(f"    {line}" for line in lines[1:])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(entry) + "\n\n")


def read_log(limit: int = 50) -> list[dict[str, str]]:
    path = config.wiki_dir() / LOG_FILE
    if not path.exists():
        return []
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r"^## \[(.+?)\]\s+(\S+)\s*\|\s*(.*)$", line)
        if match:
            if current:
                entries.append(current)
            current = {"time": match.group(1), "kind": match.group(2), "title": match.group(3), "detail": ""}
        elif current is not None and line.strip():
            current["detail"] = (current["detail"] + " " + line.strip()).strip()
    if current:
        entries.append(current)
    return list(reversed(entries))[:limit]


def ensure_overview() -> None:
    path = config.wiki_dir() / "overview.md"
    if path.exists():
        return
    write_page(
        "overview.md",
        "# 总览\n\n这个知识库还在起步阶段。收录第一批素材后，让 LLM 运行一次编译，"
        "它会自动在这里写出跨素材的综述与主线。\n",
        title="总览",
        frontmatter={"type": "overview"},
    )


def ensure_conventions() -> None:
    path = config.wiki_dir() / "conventions.md"
    if path.exists():
        return
    write_page(
        "conventions.md",
        "# 约定\n\n这里记录你希望 LLM 遵守的偏好，例如：\n\n"
        "- 回答必须标注来源页面\n"
        "- 概念页保持 300 字以内\n"
        "- 中文写作，专业术语保留英文原词\n",
        title="约定",
        frontmatter={"type": "conventions"},
    )


def ensure_vault() -> None:
    config.ensure_dirs()
    ensure_overview()
    ensure_conventions()
    index_path = config.wiki_dir() / "index.md"
    if not index_path.exists():
        write_index("# 索引\n\n知识库还是空的。收录第一篇素材后，索引会自动生成。\n")


# --------------------------------------------------------------------------- #
# raw 素材
# --------------------------------------------------------------------------- #

def save_raw(name: str, content: str, meta: dict[str, Any] | None = None) -> str:
    """把原始素材写入 raw/，返回相对路径。已存在同名文件时追加序号。"""
    raw = config.raw_dir()
    raw.mkdir(parents=True, exist_ok=True)
    stem = slugify(Path(name).stem, "source")
    target = raw / f"{stem}.md"
    counter = 2
    while target.exists():
        target = raw / f"{stem}-{counter}.md"
        counter += 1

    front = {"title": Path(name).stem, **(meta or {})}
    target.write_text(render_page(front, content), encoding="utf-8")
    return str(target.relative_to(config.vault_dir())).replace("\\", "/")


def list_raw(limit: int = 200) -> list[dict[str, Any]]:
    raw = config.raw_dir()
    if not raw.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(raw.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        meta, body = parse_frontmatter(text)
        items.append(
            {
                "path": str(path.relative_to(config.vault_dir())).replace("\\", "/"),
                "title": str(meta.get("title") or path.stem),
                "source_type": str(meta.get("source_type") or ""),
                "source_url": str(meta.get("source_url") or ""),
                "chars": len(body),
                "saved_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items


def read_raw(rel_path: str) -> str:
    rel = (rel_path or "").strip().lstrip("/")
    target = (config.vault_dir() / rel).resolve()
    root = config.raw_dir().resolve()
    if root not in target.parents:
        raise VaultError(f"只能读取 raw/ 下的素材：{rel_path}")
    if not target.exists():
        raise VaultError(f"素材不存在：{rel_path}")
    return target.read_text(encoding="utf-8", errors="ignore")


# --------------------------------------------------------------------------- #
# 检索（给 LLM 当工具用，也给 UI 用）
# --------------------------------------------------------------------------- #

def search_wiki(query: str, limit: int | None = None, kind: str | None = None) -> list[dict[str, Any]]:
    """朴素的关键词/子串检索。够用且零依赖，规模大时可以换成 qmd 之类。"""
    terms = [t for t in re.split(r"\s+", (query or "").strip().lower()) if t]
    if not terms:
        return []
    cfg = config.load_config()["search"]
    context_lines = int(cfg["context_lines"])
    limit = int(limit) if limit is not None else config.search_limit()
    results: list[dict[str, Any]] = []

    for page in list_pages(with_backlinks=False):
        if kind and page.kind != kind:
            continue
        haystack = f"{page.title}\n{page.body}".lower()
        if not all(term in haystack for term in terms):
            continue
        hits: list[dict[str, Any]] = []
        lines = page.body.splitlines()
        for index, line in enumerate(lines):
            low = line.lower()
            if not any(term in low for term in terms):
                continue
            start = max(0, index - context_lines)
            end = min(len(lines), index + context_lines + 1)
            hits.append({"line": index + 1, "text": "\n".join(lines[start:end]).strip()})
            if len(hits) >= 4:
                break
        score = sum(haystack.count(term) for term in terms)
        if page.title.lower() and any(term in page.title.lower() for term in terms):
            score += 10
        results.append(
            {
                "path": page.rel_path,
                "title": page.title,
                "kind": page.kind,
                "kind_label": KIND_LABELS.get(page.kind, page.kind),
                "score": score,
                "hits": hits,
            }
        )

    results.sort(key=lambda item: -item["score"])
    return results[:limit]


def stats() -> dict[str, Any]:
    pages = list_pages(with_backlinks=False)
    by_kind: dict[str, int] = {}
    total_chars = 0
    for page in pages:
        by_kind[page.kind] = by_kind.get(page.kind, 0) + 1
        total_chars += len(page.body)
    raw_items = list_raw(limit=100000)
    link_count = sum(len(page.links) for page in pages)
    return {
        "pages": len(pages),
        "raw_sources": len(raw_items),
        "links": link_count,
        "chars": total_chars,
        "by_kind": by_kind,
        "vault": str(config.vault_dir()),
        "log_entries": len(read_log(limit=100000)),
    }
