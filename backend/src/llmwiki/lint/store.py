"""体检报告持久化（只写 `.llmwiki/lint-report.json`）。"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llmwiki.workspace.store import atomic_write_bytes


def utc_now() -> str:
    """返回 ISO-8601 UTC 时间。"""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def report_path(vault_path: str | Path) -> Path:
    """返回 vault 内唯一体检报告路径。"""

    return Path(vault_path).expanduser().resolve() / ".llmwiki" / "lint-report.json"


def read_report(vault_path: str | Path) -> dict[str, Any] | None:
    """读取报告；损坏报告不阻断下一次扫描，按无报告处理。"""

    path = report_path(vault_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_report(
    vault_path: str | Path,
    issues: list[dict[str, Any]],
    *,
    graph_metrics: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    """原子写体检报告，并返回保存后的完整报告。"""

    kind_counts = Counter(issue["kind"] for issue in issues)
    report = {
        "generated_at": utc_now(),
        "issues": issues,
        "metrics": {
            **(graph_metrics or {}),
            "issue_count": len(issues),
            "kind_counts": dict(sorted(kind_counts.items())),
            "repairable_count": sum(issue["repairable"] and not issue["ignored"] for issue in issues),
            "vault_path": str(Path(vault_path).expanduser().resolve()),
        },
    }
    atomic_write_bytes(report_path(vault_path), json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    return report


def merge_ignored(
    issues: list[dict[str, Any]],
    previous: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """把历史 ignore 状态合并到最新扫描结果。"""

    old_issues = previous.get("issues", []) if previous else []
    ignored = {
        item["id"]: item
        for item in old_issues
        if isinstance(item, dict) and item.get("ignored") is True and isinstance(item.get("id"), str)
    }
    return [
        {
            **issue,
            "ignored": issue["id"] in ignored,
            "ignore_reason": ignored[issue["id"]].get("ignore_reason") if issue["id"] in ignored else None,
        }
        for issue in issues
    ]
