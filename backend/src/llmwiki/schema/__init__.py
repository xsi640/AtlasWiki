"""知识规范 Schema（MODULE-007）：页面类型、frontmatter 字段、校验函数、提示词。"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path


class PageType(StrEnum):
    """wiki 页面类型（ADR-011）。"""

    SOURCE = "source"
    CONCEPT = "concept"
    ENTITY = "entity"
    ANALYSIS = "analysis"


class SourceType(StrEnum):
    """页面来源类型。"""

    COMPILED = "compiled"
    QUERY_GENERATED = "query-generated"
    HUMAN = "human"


class MaterialKind(StrEnum):
    """素材类型（需求 U-03：三类）。"""

    WEB = "web"
    PDF = "pdf"
    NOTE = "note"


class MaterialStatus(StrEnum):
    """素材状态。"""

    NORMAL = "normal"
    FAILED = "failed"
    DELETED = "deleted"
    STALE = "stale"


class PageStatus(StrEnum):
    """页面状态。"""

    ACTIVE = "active"
    INVALID = "invalid"


PAGE_TYPE_DIRS: dict[PageType, str] = {
    PageType.SOURCE: "sources",
    PageType.CONCEPT: "concepts",
    PageType.ENTITY: "entities",
    PageType.ANALYSIS: "analyses",
}

VALID_PAGE_TYPES = {t.value for t in PageType}
VALID_SOURCE_TYPES = {t.value for t in SourceType}
VALID_MATERIAL_KINDS = {t.value for t in MaterialKind}
VALID_MATERIAL_STATUSES = {t.value for t in MaterialStatus}
VALID_PAGE_STATUSES = {t.value for t in PageStatus}

# 页面名规范化：中文 / 英文 / 数字 / 空格 / 连字符 / 下划线 / 点
_NAME_RE = re.compile(r"[^\w\u4e00-\u9fff\- ]")
_MAX_NAME_LEN = 120


def normalize_page_name(raw: str) -> str:
    """将任意标题转为合法页面名（同名文件去掉 .md）。"""
    name = raw.strip()
    name = _NAME_RE.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > _MAX_NAME_LEN:
        name = name[:_MAX_NAME_LEN].rstrip()
    return name


def validate_page_frontmatter(fm: dict) -> list[str]:
    """校验 frontmatter，返回错误列表（空列表 = 通过）。"""
    errors: list[str] = []
    if "title" not in fm or not fm["title"]:
        errors.append("缺少 title")
    if fm.get("type") not in VALID_PAGE_TYPES:
        errors.append(f"type 必须是 {sorted(VALID_PAGE_TYPES)}，实际: {fm.get('type')}")
    if fm.get("source_type") not in VALID_SOURCE_TYPES:
        errors.append(f"source_type 必须是 {sorted(VALID_SOURCE_TYPES)}，实际: {fm.get('source_type')}")
    if fm.get("status") and fm["status"] not in VALID_PAGE_STATUSES:
        errors.append(f"status 必须是 {sorted(VALID_PAGE_STATUSES)}，实际: {fm.get('status')}")
    return errors


# ---------------------------------------------------------------------------
# 提示词模板
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """加载提示词模板（ingest / query / lint）。"""
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"提示词模板不存在: {path}")
    return path.read_text("utf-8")


INGEST_PROMPT = """\
你是知识编译引擎。根据素材原文，生成或更新 wiki 页面。

输出 JSON（不要 markdown 代码块），包含：
{{
  "summary_page": {{"title": "...", "zone": "...", "content": "markdown 摘要正文，含 [[链接]]"}},
  "concept_pages": [{{"title": "...", "content": "...", "links": ["..."]}}],
  "entity_pages": [{{"title": "...", "content": "...", "links": ["..."]}}],
  "contradictions": [{{"page": "...", "reason": "..."}}]
}}

规则：
- 正文使用简体中文
- 交叉引用用 [[页面名]] 格式
- 每个概念页至少 3 个出链
- 不编造事实，只整理素材中的内容
"""

QUERY_PROMPT = """\
你是知识问答引擎。根据以下 wiki 页面内容回答用户问题。

页面内容：
{pages}

用户问题：{question}

规则：
- 综合多个页面作答，引用用 [[页面名]] 格式
- 知识不足时 insufficient=true，不要编造
- 回答使用简体中文
"""

LINT_PROMPT = """\
你是知识库体检引擎。根据以下 wiki 页面信息，检测问题。

页面列表：
{pages}

输出 JSON（不要 markdown 代码块）：
{{
  "issues": [
    {{"kind": "contradiction|orphan|dead_link|missing_index|zone_mix", "page": "...", "detail": "...", "suggestion": "..."}}
  ]
}}
"""
