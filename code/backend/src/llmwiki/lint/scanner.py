"""只读体检扫描：五类常见知识库结构问题（TASK-029）。"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from llmwiki.schema import PageType
from llmwiki.workspace.links import LinkIndex
from llmwiki.workspace.store import Page, WikiStore

REPAIRABLE_KINDS = {"dead_link", "missing_index"}
SEMANTIC_KINDS = {"contradiction", "orphan", "zone_mix"}
ISSUE_KINDS = sorted(REPAIRABLE_KINDS | SEMANTIC_KINDS)


def _issue_id(kind: str, page: str, scope: str = "") -> str:
    """生成稳定 ID；重扫后同一个问题仍可继续忽略或修复。"""

    digest = hashlib.sha1(f"{kind}\n{page}\n{scope}".encode()).hexdigest()
    return f"issue-{digest[:12]}"


def _base_issue(*, issue_id: str, kind: str, page: str, detail: str, suggestion: str) -> dict[str, Any]:
    return {
        "id": issue_id,
        "kind": kind,
        "page": page,
        "detail": detail,
        "suggestion": suggestion,
        "repairable": kind in REPAIRABLE_KINDS,
        "ignored": False,
        "ignore_reason": None,
    }


def _contradiction_text(value: Any) -> str:
    """把 frontmatter 中的矛盾描述压缩为报告文本。"""

    if value is None or value == "" or value == [] or value == {}:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {item}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return "; ".join(text for item in value if (text := _contradiction_text(item)))
    return str(value)


def _index_entries(content: str) -> set[str]:
    """解析索引正文中的 wiki 链接。"""

    entries: set[str] = set()
    for line in content.splitlines():
        location = line.find("[[")
        end = line.find("]]", location + 2)
        if location >= 0 and end > location:
            target = line[location + 2 : end].partition("|")[0].strip()
            if target:
                entries.add(target)
    return entries


class LintScanner:
    """扫描 vault 页面、链接和索引；所有方法都不写入页面。"""

    async def scan(self, vault_path: str | Path) -> list[dict[str, Any]]:
        """只读扫描并返回按类型和页面名稳定排序的问题列表。"""

        store = WikiStore(vault_path)
        if not store.initialized:
            return []

        pages = store.read_pages()
        index = store.link_index()
        issues = [
            *self._find_contradictions(pages),
            *self._find_orphans(pages, index),
            *self._find_dead_links(pages),
            *self._find_missing_index(store, pages),
            *self._find_zone_mixes(pages),
        ]
        return sorted(issues, key=lambda item: (ISSUE_KINDS.index(item["kind"]), item["page"], item["id"]))

    @staticmethod
    def metrics(pages: list[Page], index: LinkIndex) -> dict[str, float | int]:
        """计算 SC-3 要求的孤儿占比与平均出链指标。"""

        out_counts = [len(index.out_links.get(page.name, [])) for page in pages]
        orphan_count = sum(
            not index.out_links.get(page.name) and not index.back_links.get(page.name)
            for page in pages
        )
        return {
            "page_count": len(pages),
            "orphan_count": orphan_count,
            "orphan_ratio": round(orphan_count / len(pages), 6) if pages else 0.0,
            "average_out_links": round(sum(out_counts) / len(pages), 6) if pages else 0.0,
        }

    @staticmethod
    def _find_contradictions(pages: list[Page]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for page in pages:
            description = _contradiction_text(page.metadata.get("contradictions"))
            if description:
                issues.append(
                    _base_issue(
                        issue_id=_issue_id("contradiction", page.name, description),
                        kind="contradiction",
                        page=page.name,
                        detail=description,
                        suggestion="核对原始素材，改写冲突表述或在正文中说明适用条件",
                    )
                )
        return issues

    @staticmethod
    def _find_orphans(pages: list[Page], index: LinkIndex) -> list[dict[str, Any]]:
        return [
            _base_issue(
                issue_id=_issue_id("orphan", page.name),
                kind="orphan",
                page=page.name,
                detail="页面没有任何有效出链，也没有被其他页面引用",
                suggestion="补充相关页面链接，或将该页并入已有主题",
            )
            for page in pages
            if not index.out_links.get(page.name) and not index.back_links.get(page.name)
        ]

    @staticmethod
    def _find_dead_links(pages: list[Page]) -> list[dict[str, Any]]:
        known = {page.name for page in pages}
        issues: list[dict[str, Any]] = []
        for page in pages:
            targets = dict.fromkeys(link.target for link in page.links if link.target)
            for target in targets:
                if target not in known:
                    issues.append(
                        _base_issue(
                            issue_id=_issue_id("dead_link", page.name, target),
                            kind="dead_link",
                            page=page.name,
                            detail=f"出链 [[{target}]] 指向不存在的页面",
                            suggestion=f"创建页面「{target}」，或把链接改为已存在的相关页面",
                        )
                    )
        return issues

    @staticmethod
    def _find_missing_index(store: WikiStore, pages: list[Page]) -> list[dict[str, Any]]:
        index_path = store.wiki_dir / "index.md"
        entries = _index_entries(index_path.read_text("utf-8")) if index_path.is_file() else set()
        return [
            _base_issue(
                issue_id=_issue_id("missing_index", page.name),
                kind="missing_index",
                page=page.name,
                detail="页面未出现在 wiki/index.md",
                suggestion="重建页面索引以包含该页面",
            )
            for page in pages
            if page.name not in entries
        ]

    @staticmethod
    def _find_zone_mixes(pages: list[Page]) -> list[dict[str, Any]]:
        by_zone: dict[str, list[Page]] = defaultdict(list)
        for page in pages:
            zone = page.metadata.get("zone")
            if isinstance(zone, str) and zone.strip():
                by_zone[zone.strip()].append(page)

        issues: list[dict[str, Any]] = []
        for zone in sorted(by_zone):
            zone_pages = by_zone[zone]
            type_counts = Counter(str(page.metadata.get("type", "")) for page in zone_pages)
            concept_ratio = type_counts[PageType.CONCEPT.value] / len(zone_pages)
            if len(zone_pages) >= 3 and concept_ratio < 0.3:
                summary = ", ".join(f"{kind}: {count}" for kind, count in sorted(type_counts.items()))
                issues.append(
                    _base_issue(
                        issue_id=_issue_id("zone_mix", zone, summary),
                        kind="zone_mix",
                        page=zone,
                        detail=f"分区包含 {len(zone_pages)} 个页面，概念页占比 {concept_ratio:.1%}（{summary}）",
                        suggestion="重新划分分区，或补充概念页以形成稳定知识结构",
                    )
                )
        return issues
