"""页面内容 diff 生成。"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PageDiff:
    """一份可直接返回给前端的页面差异。"""

    page: str
    diff: str
    has_changes: bool


def unified_content_diff(
    old_content: str,
    new_content: str,
    *,
    from_label: str = "a",
    to_label: str = "b",
    context_lines: int = 3,
) -> str:
    """使用标准库生成 unified diff；内容相同时返回空字符串。"""
    if context_lines < 0:
        raise ValueError("context_lines 不能为负数")

    lines = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=from_label,
        tofile=to_label,
        n=context_lines,
    )
    return "".join(lines)


class PageDiffService:
    """对比旧、新页面内容，供 API 层组合页面名与响应模型。"""

    def diff(
        self,
        page: str,
        old_content: str,
        new_content: str,
        *,
        vault_path: Path | str | None = None,
        context_lines: int = 3,
    ) -> PageDiff:
        """生成页面级 unified diff。"""
        text = unified_content_diff(
            old_content,
            new_content,
            from_label=f"a/{page}",
            to_label=f"b/{page}",
            context_lines=context_lines,
        )
        label = str(Path(page))
        return PageDiff(page=label, diff=text, has_changes=bool(text))
