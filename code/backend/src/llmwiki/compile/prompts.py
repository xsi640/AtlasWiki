"""编译提示词填充（TASK-013）。"""

from __future__ import annotations

from llmwiki.schema import INGEST_PROMPT


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
