"""确定性编译器 —— 没有配置大模型 API Key 时的兜底。

它仍然严格遵循 LLM Wiki 的**结构**：raw/ 素材 → wiki/ 页面 + 双链 + 索引 + 日志。
区别只是页面正文由「关键词聚合的原文摘录」构成，而不是 LLM 撰写的百科条目。
一旦填上 `llm.api_key`，同样的素材会被 LLM 重写成真正的百科条目。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Callable, Iterable

from . import config, vault
from .textutil import keywords as extract_keywords
from .textutil import clip, slugify, strip_markdown

ProgressFn = Callable[[str], None]

_ENTITY_HINT = re.compile(r"(公司|团队|集团|实验室|大学|研究院|平台|模型|框架|语言|协议|系统|引擎)$")

# 采集器注入的元信息行（「> 来源：… · 日期 …」「> 原链接：…」等）。
# 它们不是正文，做摘要时必须跳过。
_META_LINE = re.compile(r"^(来源|原链接|作者|日期|原始素材|类型|站点|发布)\s*[:：]")


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def _noop(_: str) -> None:
    return None


def _paragraphs(text: str) -> list[str]:
    """按空行切段，再逐段去掉 Markdown 标记。

    顺序很重要：必须**先切段、后清洗**。反过来先 strip_markdown 会把段落边界
    一起抹掉，切出来就只剩一整块（历史上标题、来源行、正文首段因此被粘成一段）。
    """
    out: list[str] = []
    for block in re.split(r"\n\s*\n", text or ""):
        clean = re.sub(r"\s+", " ", strip_markdown(block)).strip()
        if len(clean) >= 30:
            out.append(clean)
    return out


def _lead_paragraphs(body: str, title: str, limit: int = 6) -> list[str]:
    """正文开头几段，跳过标题行与采集器注入的元信息行。"""
    out: list[str] = []
    for para in _paragraphs(body):
        if para == title or _META_LINE.match(para):
            continue
        out.append(para)
        if len(out) >= limit:
            break
    return out


def _keyword_text(body: str) -> str:
    """抽关键词时要去掉我们自己加的标题与来源行，否则「原链接」这类词会变成概念。"""
    lines = (body or "").split("\n")
    kept: list[str] = []
    for index, line in enumerate(lines):
        if index < 12 and re.match(r"^\s*(#{1,2}\s|>\s|来源[:：]|原链接[:：])", line):
            continue
        kept.append(line)
    return "\n".join(kept)


def _source_title(raw_rel: str, meta: dict[str, Any], body: str) -> str:
    title = str(meta.get("title") or "").strip()
    if title and title != "source":
        return title
    match = re.search(r"^\s{0,3}#\s+(.+)$", body, re.M)
    if match:
        return match.group(1).strip()
    return vault.slug_of(raw_rel)


def _iter_raw() -> Iterable[tuple[str, dict[str, Any], str]]:
    """遍历所有原始素材，产出 (相对路径, frontmatter, 正文)。"""
    raw_root = config.raw_dir()
    if not raw_root.exists():
        return []
    items = []
    for path in sorted(raw_root.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        meta, body = vault.parse_frontmatter(text)
        rel = str(path.relative_to(config.vault_dir())).replace("\\", "/")
        items.append((rel, meta, body))
    return items


# --------------------------------------------------------------------------- #
# 素材页
# --------------------------------------------------------------------------- #

def _write_source_page(raw_rel: str, meta: dict[str, Any], body: str) -> str:
    title = _source_title(raw_rel, meta, body)
    slug = slugify(title, vault.slug_of(raw_rel))
    rel = f"sources/{slug}.md"

    plain = strip_markdown(body)
    lead = _lead_paragraphs(body, title)
    top_keywords = extract_keywords(_keyword_text(body), 10)
    # 摘要取正文段落，不能用 plain —— plain 的开头是标题和采集器注入的
    # 「来源 / 日期 / 原链接」行，直接截断会得到「来源：… 原链接：https://…」
    # 这种零信息量的摘要，还会从单词中间断开。
    summary_text = clip(" ".join(lead), 120) or clip(plain, 120)

    source_url = str(meta.get("source_url") or "")
    source_type = str(meta.get("source_type") or "")
    author = str(meta.get("author") or "")

    lines = [f"# {title}", ""]
    lines.append(f"> 原始素材：`{raw_rel}`" + (f" · 类型 {source_type}" if source_type else ""))
    if source_url:
        lines.append(f"> 原链接：{source_url}")
    if author:
        lines.append(f"> 作者：{author}")
    lines.append("")
    lines.append("## 内容摘要")
    lines.append("")
    lines.append("\n\n".join(lead) if lead else plain[:800])
    lines.append("")
    if top_keywords:
        # 只给真正存在的概念页加双链，避免制造一堆失效链接
        rendered = []
        for kw in top_keywords:
            rel_kw = f"concepts/{slugify(kw, 'concept')}.md"
            rendered.append(f"[[{kw}]]" if vault.page_exists(rel_kw) else kw)
        lines.append("## 关键概念")
        lines.append("")
        lines.append(" ".join(rendered))
        lines.append("")

    page = vault.write_page(
        rel,
        "\n".join(lines),
        title=title,
        frontmatter={
            "type": "source",
            "tags": top_keywords[:6],
            "summary": summary_text,
            "sources": [raw_rel],
            "source_url": source_url,
        },
    )
    return page.rel_path


# --------------------------------------------------------------------------- #
# 概念页 / 实体页
# --------------------------------------------------------------------------- #

def concept_candidates() -> dict[str, list[tuple[str, str]]]:
    """概念 → [(素材页 rel, 摘录)]。

    **这是「一个词值不值得建概念页」的唯一判定标准**，lint 也复用它，
    以保证体检结论与编译器行为一致（否则 lint 会反复提示编译器有意剔除的泛词）。

    入选条件：
      * 至少被 2 篇素材提到
      * 在全部素材里累计出现 ≥ 3 次（只在模板样板里出现一两次的不是概念）
      * 不是那种「几乎所有素材都会出现」的泛词
    """
    index: dict[str, list[tuple[str, str]]] = defaultdict(list)
    occurrences: Counter[str] = Counter()
    items = list(_iter_raw())
    for raw_rel, _meta, body in items:
        ktext = _keyword_text(body)
        lowered = ktext.lower()
        for kw in extract_keywords(ktext, 12):
            index[kw].append((raw_rel, ""))
            occurrences[kw] += lowered.count(kw.lower())

    total = len(items) or 1
    result: dict[str, list[tuple[str, str]]] = {}
    for kw, refs in index.items():
        if len(refs) < 2:
            continue
        if occurrences[kw] < 3:
            continue
        if total >= 4 and len(refs) / total > 0.75:
            continue
        result[kw] = refs
    return result


def _excerpts_for(term: str, limit: int = 4) -> list[tuple[str, str]]:
    """在所有素材里找出提到该概念的段落，返回 [(素材标题, 段落)]。"""
    found: list[tuple[str, str]] = []
    lowered = term.lower()
    for raw_rel, meta, body in _iter_raw():
        title = _source_title(raw_rel, meta, body)
        for paragraph in _paragraphs(body):
            if lowered in paragraph.lower():
                found.append((title, paragraph[:400]))
                break
        if len(found) >= limit:
            break
    return found


def _write_concept_page(term: str, progress: ProgressFn = _noop) -> str | None:
    excerpts = _excerpts_for(term)
    if len(excerpts) < 2:
        return None
    rel = f"concepts/{slugify(term, 'concept')}.md"
    progress(f"生成概念页 {term}")

    lines = [
        f"# {term}",
        "",
        "> 本页由确定性编译器聚合生成（当前未配置大模型）。配置 `llm.api_key` 后，",
        "> 这里会被重写成由 LLM 撰写的百科条目。",
        "",
        "## 相关素材摘录",
        "",
    ]
    for title, paragraph in excerpts:
        lines.append(f"### [[{title}]]")
        lines.append("")
        lines.append(f"> {paragraph}")
        lines.append("")

    page = vault.write_page(
        rel,
        "\n".join(lines),
        title=term,
        frontmatter={
            "type": "concept",
            "tags": [term],
            "summary": f"聚合自 {len(excerpts)} 篇素材",
            "sources": [],
        },
    )
    return page.rel_path


def _write_entity_page(name: str, progress: ProgressFn = _noop) -> str | None:
    refs: list[tuple[str, str]] = []
    for raw_rel, meta, body in _iter_raw():
        author = str(meta.get("author") or "").strip()
        if author and author == name:
            refs.append((_source_title(raw_rel, meta, body), raw_rel))
    if not refs:
        return None
    rel = f"entities/{slugify(name, 'entity')}.md"
    progress(f"生成实体页 {name}")
    lines = [f"# {name}", "", f"{name} 是知识库中出现的作者 / 创作者。", "", "## 相关素材", ""]
    for title, _ in refs:
        lines.append(f"- [[{title}]]")
    page = vault.write_page(
        rel,
        "\n".join(lines),
        title=name,
        frontmatter={"type": "entity", "tags": ["作者"], "summary": f"关联 {len(refs)} 篇素材"},
    )
    return page.rel_path


# --------------------------------------------------------------------------- #
# 总览
# --------------------------------------------------------------------------- #

def _write_overview() -> None:
    concepts = concept_candidates()
    raw_items = list(_iter_raw())
    lines = [
        "# 总览",
        "",
        f"知识库当前包含 **{len(raw_items)}** 篇原始素材，"
        f"**{len(concepts)}** 个跨素材概念。",
        "",
    ]
    if concepts:
        ranked = sorted(concepts.items(), key=lambda kv: -len(kv[1]))[:20]
        lines.append("## 出现频次最高的概念")
        lines.append("")
        for term, refs in ranked:
            lines.append(f"- [[{term}]] — 出现在 {len(refs)} 篇素材中")
        lines.append("")
    lines.append("## 素材清单")
    lines.append("")
    for raw_rel, meta, body in raw_items:
        lines.append(f"- [[{_source_title(raw_rel, meta, body)}]]")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "> 这是确定性编译器生成的骨架。在 `config.yaml` 里填入 `llm.api_key` 后，"
        "重新收录或执行一次「重建 wiki」，LLM 会把这些页面重写成真正的百科条目，"
        "并补上矛盾标注、交叉引用与专题分析。"
    )
    vault.write_page("overview.md", "\n".join(lines), title="总览", frontmatter={"type": "overview"})


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #

def compile_source(raw_rel: str, progress: ProgressFn = _noop) -> dict[str, Any]:
    """把一篇新素材编译进 wiki（确定性版本）。"""
    raw_root = config.raw_dir()
    path = (config.vault_dir() / raw_rel).resolve()
    if not path.exists() or raw_root.resolve() not in path.parents:
        raise vault.VaultError(f"素材不存在：{raw_rel}")

    text = path.read_text(encoding="utf-8", errors="ignore")
    meta, body = vault.parse_frontmatter(text)
    title = _source_title(raw_rel, meta, body)
    created: list[str] = []

    # 先建概念页，再写素材页 —— 这样素材页里的 [[双链]] 才能正确解析。
    #
    # 候选词必须用和全量重建同一个判定函数（concept_candidates），否则增量收录会
    # 绕过质量门槛：只看「新素材自己的 top-8 关键词」会把「每次」「复利」这类词
    # 也建成概念页。这里改成全局候选 + 只建尚不存在的页面 ——
    # 新素材的加入可能让某个词首次达标（从 1 篇变 2 篇），这正是增量编译该做的事。
    for term in concept_candidates():
        rel_candidate = f"concepts/{slugify(term, 'concept')}.md"
        if vault.page_exists(rel_candidate):
            continue
        try:
            rel = _write_concept_page(term, progress)
        except Exception:
            rel = None
        if rel and rel not in created:
            created.append(rel)

    author = str(meta.get("author") or "").strip()
    if author:
        try:
            rel = _write_entity_page(author, progress)
            if rel and rel not in created:
                created.append(rel)
        except Exception:
            pass

    progress(f"生成素材页《{title}》")
    source_page = _write_source_page(raw_rel, meta, body)

    progress("更新总览与索引")
    # 顺序很重要：总览要先落盘，rebuild_index 才能把它收录进「总览」小节
    _write_overview()
    vault.rebuild_index()
    vault.append_log("ingest", f"{title} → 素材页 + {len(created)} 个概念/实体页（确定性编译）")

    return {"source_page": source_page, "created": created, "title": title}


def compile_all(progress: ProgressFn = _noop) -> dict[str, Any]:
    """全量重建 wiki（确定性版本）。用于首次导入已有 raw/ 目录。"""
    items = list(_iter_raw())
    if not items:
        vault.ensure_vault()
        return {"sources": 0, "pages": 0}

    progress(f"发现 {len(items)} 篇素材，开始编译")
    created: list[str] = []

    # 1) 概念页
    concepts = concept_candidates()
    progress(f"发现 {len(concepts)} 个跨素材概念")
    for term in concepts:
        rel = _write_concept_page(term, progress)
        if rel and rel not in created:
            created.append(rel)

    # 2) 实体页
    authors = {str(meta.get("author") or "").strip() for _, meta, _ in items}
    for author in filter(None, authors):
        rel = _write_entity_page(author, progress)
        if rel and rel not in created:
            created.append(rel)

    # 3) 素材页（此时概念页已就位，双链可以正确解析）
    for raw_rel, meta, body in items:
        title = _source_title(raw_rel, meta, body)
        progress(f"生成素材页《{title}》")
        rel = _write_source_page(raw_rel, meta, body)
        if rel not in created:
            created.append(rel)

    progress("重建总览与索引")
    # 顺序很重要：总览要先落盘，rebuild_index 才能把它收录进「总览」小节
    _write_overview()
    vault.rebuild_index()
    vault.append_log("ingest", f"全量重建：{len(items)} 篇素材 → {len(created)} 个页面（确定性编译）")

    return {"sources": len(items), "pages": len(created)}
