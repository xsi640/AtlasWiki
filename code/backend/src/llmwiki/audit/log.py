"""`wiki/log.md` 的 append-only 操作日志。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LOG_RELATIVE_PATH = Path("wiki") / "log.md"


@dataclass(frozen=True)
class LogEntry:
    """一条已写入操作日志的记录。"""

    timestamp: str
    operation_type: str
    affected_pages: tuple[str, ...]
    reason: str
    text: str


def _single_line(value: str) -> str:
    """将任意业务字段压成单行，避免破坏一行一条的日志格式。"""
    normalized = " ".join(value.split())
    return normalized.replace("|", "\\|")


def format_log_line(
    timestamp: str,
    operation_type: str,
    affected_pages: Sequence[str],
    reason: str = "",
) -> str:
    """生成任务规定的单行日志格式。"""
    pages_text = ", ".join(_single_line(str(page)) for page in affected_pages)
    return (
        f"## {_single_line(timestamp)} | "
        f"{_single_line(operation_type)} | "
        f"{pages_text} | "
        f"{_single_line(reason)}"
    )


class AuditLogger:
    """只负责向 vault 内的操作日志追加内容。"""

    def __init__(self, vault_path: Path | str | None = None) -> None:
        self._vault_path = Path(vault_path) if vault_path is not None else None

    @property
    def log_path(self) -> Path:
        """返回实际日志文件路径。"""
        if self._vault_path is None:
            raise ValueError("AuditLogger 需要显式 vault_path，或改用 service 层解析配置")
        return self._vault_path / LOG_RELATIVE_PATH

    def append(
        self,
        operation_type: str,
        affected_pages: Sequence[str],
        reason: str = "",
        *,
        timestamp: datetime | str | None = None,
    ) -> LogEntry:
        """追加一条记录；文件不存在时创建，已有内容不会被修改。"""
        if not operation_type.strip():
            raise ValueError("operation_type 不能为空")

        timestamp_value = timestamp or datetime.now().astimezone()
        timestamp_text = (
            timestamp_value.isoformat(timespec="seconds")
            if isinstance(timestamp_value, datetime)
            else str(timestamp_value)
        )
        line = format_log_line(timestamp_text, operation_type, affected_pages, reason)

        target = self.log_path
        target.parent.mkdir(parents=True, exist_ok=True)
        prefix = "" if not target.exists() or target.read_text("utf-8").endswith("\n") else "\n"
        # O_APPEND 保证并发调用时只追加，不覆盖既有日志。
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{prefix}{line}\n")

        return LogEntry(
            timestamp=timestamp_text,
            operation_type=operation_type,
            affected_pages=tuple(affected_pages),
            reason=reason,
            text=line,
        )
