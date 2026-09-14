"""Lint —— 知识库健康体检。

结构性问题用确定性检查（快、零成本）；语义问题（矛盾、陈旧说法、数据缺口）
交给 LLM 用 LINT_PROMPT 处理。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from . import compiler, config, vault


def structural_lint() -> dict[str, Any]:
    """不需要 LLM 的结构性检查。"""
    pages = vault.list_pages(with_backlinks=True)
    link_map = vault.build_link_map(pages)
    cfg = config.load_config()["lint"]
    stale_days = int(cfg["stale_days"])
    cutoff = datetime.now() - timedelta(days=stale_days)

    orphans: list[dict[str, str]] = []
    broken: list[dict[str, str]] = []
    stale: list[dict[str, str]] = []
    missing_meta: list[dict[str, str]] = []
    thin: list[dict[str, str]] = []
    linked_targets: set[str] = set()

    for page in pages:
        if page.kind != "root" and not page.backlinks:
            orphans.append({"path": page.rel_path, "title": page.title})
        for link in page.links:
            target = vault.resolve_link(link, link_map)
            if target:
                linked_targets.add(target)
            else:
                broken.append({"path": page.rel_path, "title": page.title, "link": link})
        if page.kind not in ("root",):
            summary = str(page.frontmatter.get("summary") or "").strip()
            if not summary:
                missing_meta.append({"path": page.rel_path, "title": page.title, "missing": "summary"})
        updated = str(page.frontmatter.get("updated") or "")
        if updated:
            try:
                if datetime.strptime(updated[:10], "%Y-%m-%d") < cutoff:
                    stale.append({"path": page.rel_path, "title": page.title, "updated": updated})
            except Exception:
                pass
        if page.kind in ("concepts", "entities") and len(page.body) < 150:
            thin.append({"path": page.rel_path, "title": page.title, "chars": len(page.body)})

    # 被反复提及但没有独立页面的概念。
    # 复用编译器的判定标准（concept_candidates），保证体检结论与编译器行为一致 ——
    # 否则会反复提示编译器有意剔除的泛词（「素材」「知识库」「markdown」之类）。
    candidates = compiler.concept_candidates()
    missing_concepts = sorted(
        (
            {"term": term, "mentions": len(refs)}
            for term, refs in candidates.items()
            if not vault.resolve_link(term, link_map)
        ),
        key=lambda item: -item["mentions"],
    )[:20]

    unindexed = []
    index_body = vault.read_index()
    for page in pages:
        if page.rel_path == "index.md":
            continue
        if page.title and f"[[{page.title}]]" not in index_body and page.rel_path not in index_body:
            unindexed.append({"path": page.rel_path, "title": page.title})

    issues = sum(
        len(x)
        for x in (orphans, broken, stale, missing_meta, thin, missing_concepts, unindexed)
    )
    return {
        "pages": len(pages),
        "issues": issues,
        "orphans": orphans[:50],
        "broken_links": broken[:50],
        "stale": stale[:50],
        "missing_meta": missing_meta[:50],
        "thin_pages": thin[:50],
        "missing_concepts": missing_concepts,
        "unindexed": unindexed[:50],
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [f"# 结构体检报告", "", f"共 {report['pages']} 个页面，发现 {report['issues']} 处待处理项。", ""]

    def section(title: str, items: list, render) -> None:
        lines.append(f"## {title}（{len(items)}）")
        lines.append("")
        if not items:
            lines.append("无。")
        else:
            lines.extend(render(item) for item in items[:20])
        lines.append("")

    section("孤儿页（没有任何入链）", report["orphans"], lambda i: f"- `{i['path']}` 《{i['title']}》")
    section(
        "失效链接",
        report["broken_links"],
        lambda i: f"- `{i['path']}` 中的 `[[{i['link']}]]` 指向不存在的页面",
    )
    section("陈旧页面", report["stale"], lambda i: f"- `{i['path']}` 最后更新 {i['updated']}")
    section("缺少摘要", report["missing_meta"], lambda i: f"- `{i['path']}` 《{i['title']}》")
    section("内容过短", report["thin_pages"], lambda i: f"- `{i['path']}` 《{i['title']}》仅 {i['chars']} 字符")
    section(
        "达到概念标准但没有独立页面",
        report["missing_concepts"],
        lambda i: f"- 「{i['term']}」出现在 {i['mentions']} 篇素材中",
    )
    section("未进入索引", report["unindexed"], lambda i: f"- `{i['path']}` 《{i['title']}》")

    return "\n".join(lines).strip() + "\n"


def save_report(report: dict[str, Any]) -> str:
    content = format_report(report)
    vault.write_page(
        "analyses/health-check.md",
        content,
        title="结构体检报告",
        frontmatter={"type": "analysis", "tags": ["lint"], "summary": f"{report['issues']} 处待处理项"},
    )
    # 报告本身也是一个页面，写完后重建索引，避免下次体检把它报成「未进入索引」
    vault.rebuild_index()
    return "analyses/health-check.md"
