"""Obsidian 风格 `[[链接]]` 解析与链接索引。"""

from __future__ import annotations

from dataclasses import dataclass
from re import compile


@dataclass(frozen=True, slots=True)
class WikiLink:
    """一次链接出现记录；target 是页面名，label 是显示文本。"""

    target: str
    label: str
    line: int
    column: int


# 只识别双括号，避免误判 Markdown 中的普通方括号。
_WIKI_LINK_RE = compile(r"(?<!\[)\[\[([^\[\]]+)\]\](?!\])")


def extract_links(content: str) -> list[WikiLink]:
    """按出现顺序解析正文链接，支持 `[[页面名|显示文本]]`。"""

    links: list[WikiLink] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        for match in _WIKI_LINK_RE.finditer(line):
            raw = match.group(1).strip()
            if not raw:
                continue
            target, separator, display = raw.partition("|")
            target = target.strip()
            if not target:
                continue
            links.append(
                WikiLink(
                    target=target,
                    label=(display if separator else target).strip(),
                    line=line_number,
                    column=match.start() + 1,
                )
            )
    return links


def _unique[T](items: list[T]) -> list[T]:
    """保持首次出现顺序去重，供图谱和反链面板使用。"""

    return list(dict.fromkeys(items))


@dataclass(frozen=True, slots=True)
class LinkIndex:
    """页面名到出链/反链的只读索引。"""

    nodes: tuple[str, ...]
    out_links: dict[str, list[str]]
    back_links: dict[str, list[str]]
    edges: tuple[tuple[str, str], ...]


def build_link_index(page_names: list[str], page_links: dict[str, list[str]]) -> LinkIndex:
    """基于页面及其解析出的目标构建双向链接索引。"""

    known = set(page_names)
    out: dict[str, list[str]] = {name: _unique(page_links.get(name, [])) for name in page_names}
    back: dict[str, list[str]] = {name: [] for name in page_names}
    edges: list[tuple[str, str]] = []

    for source in page_names:
        for target in out[source]:
            if target in known:
                back[target].append(source)
                edges.append((source, target))

    # 以页面名排序，保证测试和 API 输出稳定。
    ordered_nodes = tuple(sorted(known))
    ordered_out = {name: out[name] for name in ordered_nodes}
    ordered_back = {name: _unique(back[name]) for name in ordered_nodes}
    return LinkIndex(
        nodes=ordered_nodes,
        out_links=ordered_out,
        back_links=ordered_back,
        edges=tuple(edges),
    )
