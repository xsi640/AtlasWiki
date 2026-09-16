"""组合日志与 git 提交，提供写入任务完成后的统一审计入口。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from atlaswiki.config import config_store

from .diff import PageDiff, PageDiffService
from .git_ops import GitCommitResult, GitOperations
from .log import LOG_RELATIVE_PATH, AuditLogger, LogEntry


@dataclass(frozen=True)
class TaskAuditResult:
    """完整任务审计结果：日志记录 + 自动 commit。"""

    log_entry: LogEntry
    commit: GitCommitResult
    log_relative_path: str


class AuditService:
    """写入任务完成后先追加操作日志，再把日志与任务文件一起提交。"""

    def __init__(
        self,
        *,
        logger: AuditLogger | None = None,
        git: GitOperations | None = None,
        diff_service: PageDiffService | None = None,
    ) -> None:
        self._logger = logger or AuditLogger()
        self._git = git or GitOperations()
        self._diff = diff_service or PageDiffService()

    def record_task_completion(
        self,
        *,
        operation_type: str,
        affected_pages: Sequence[str],
        affected_files: Sequence[Path | str],
        reason: str = "",
        vault_path: Path | str | None = None,
    ) -> TaskAuditResult:
        """记录并自动 commit；无远端不会影响本步骤。"""
        resolved_vault = (
            Path(vault_path).expanduser().resolve()
            if vault_path is not None
            else Path(config_store.load().vault_path).expanduser().resolve()
        )
        log_entry = AuditLogger(resolved_vault).append(
            operation_type,
            affected_pages,
            reason,
        )
        commit = self._git.commit_task(
            operation_type=operation_type,
            affected_files=affected_files,
            reason=reason or ", ".join(affected_pages),
            vault_path=resolved_vault,
        )
        return TaskAuditResult(
            log_entry=log_entry,
            commit=commit,
            log_relative_path=LOG_RELATIVE_PATH.as_posix(),
        )

    def page_diff(
        self,
        page: str,
        old_content: str,
        new_content: str,
        *,
        vault_path: Path | str | None = None,
        context_lines: int = 3,
    ) -> PageDiff:
        """生成页面级 diff。"""
        return self._diff.diff(
            page,
            old_content,
            new_content,
            vault_path=vault_path,
            context_lines=context_lines,
        )
