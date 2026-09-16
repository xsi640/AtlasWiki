"""编译提示词填充（TASK-013）。"""

from __future__ import annotations

from atlaswiki.schema import INGEST_PROMPT


def build_compile_messages(
    *,
    source_title: str,
    source_content: str,
    existing_pages: list[str] | None = None,
) -> list[dict[str, str]]:
    """用冻结的 INGEST_PROMPT 组装一次 JSON Mode 请求。"""

    names = [name for name in (existing_pages or []) if name.strip()]
    existing_block = ""
    if names:
        # 只给页面名作为增量更新上下文，避免把旧正文重复塞进请求。
        joined = "\n".join(f"- {name}" for name in names)
        existing_block = f"\n\n当前 wiki 已有页面：\n{joined}"
    source_block = (
        f"\n\n素材标题：{source_title}\n\n素材原文：\n{source_content.strip()}"
        f"{existing_block}"
    )
    return [
        {"role": "system", "content": INGEST_PROMPT},
        {"role": "user", "content": source_block},
    ]


_SEGMENT_PROMPT = """\
你是知识编译引擎的分段摘要器。素材太长，已被拆成多个片段；\
你会依次看到其中一个片段。请只输出 JSON（不要 markdown 代码块）：

{"summary": "本段事实要点的浓缩摘要（markdown，保留关键数字与结论）", "concepts": ["值得建概念页的主题"], "entities": ["值得建实体页的专有名词"]}

规则：
- 只根据本段内容作答，不要推测其他片段。
- concepts / entities 给出名称即可，不要写正文。
- 宁缺毋滥：泛词（方法、系统、问题）不要收录。"""


def build_segment_messages(
    *,
    source_title: str,
    segment: str,
    index: int,
    total: int,
) -> list[dict[str, str]]:
    """为长文分段摘要组装一次 JSON Mode 请求（TASK-015）。"""

    user_block = (
        f"素材标题：{source_title}\n"
        f"片段 {index}/{total}：\n\n{segment.strip()}"
    )
    return [
        {"role": "system", "content": _SEGMENT_PROMPT},
        {"role": "user", "content": user_block},
    ]
