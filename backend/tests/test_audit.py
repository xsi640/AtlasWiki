"""TASK-005 审计与 git 底座验收测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlaswiki.audit import AuditLogger, AuditService, GitOperations, unified_content_diff
from atlaswiki.errors import AppError, ErrorCode


def write_page(vault: Path, name: str, content: str) -> Path:
    """创建一个测试页面并返回其路径。"""
    path = vault / "wiki" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_record_task_completion_appends_log_and_commits_affected_file_count(tmp_path: Path) -> None:
    """写入任务完成后应记录一行审计日志，并生成包含类型和文件数的 commit。"""
    vault = tmp_path / "vault"
    page = write_page(vault, "alpha.md", "# Alpha\n")
    index = write_page(vault, "index.md", "# Index\n")
    service = AuditService()

    result = service.record_task_completion(
        vault_path=vault,
        operation_type="compile",
        affected_pages=["Alpha", "Index"],
        affected_files=[page, index],
        reason="同步网页素材",
    )

    log_text = (vault / "wiki" / "log.md").read_text(encoding="utf-8")
    assert log_text.startswith("## ")
    assert " | compile | Alpha, Index | 同步网页素材\n" in log_text
    assert result.log_entry.text in log_text
    assert result.commit.affected_file_count == 2
    assert result.commit.message == "task=compile; affected_files=2; reason=同步网页素材"
    assert "wiki/log.md" in result.commit.changed_files
    assert result.commit.commit_hash


def test_audit_log_is_append_only(tmp_path: Path) -> None:
    """连续记录时必须保留全部既有日志，且每次记录追加一行。"""
    vault = tmp_path / "vault"
    page = write_page(vault, "alpha.md", "# Alpha\n")
    service = AuditService()

    first = service.record_task_completion(
        vault_path=vault,
        operation_type="compile",
        affected_pages=["Alpha"],
        affected_files=[page],
        reason="第一次导入",
    )
    first_log = (vault / "wiki" / "log.md").read_text(encoding="utf-8")
    (vault / "wiki" / "second.md").write_text("# Second\n", encoding="utf-8")
    service.record_task_completion(
        vault_path=vault,
        operation_type="human_edit",
        affected_pages=["Second"],
        affected_files=[vault / "wiki" / "second.md"],
        reason="人工补录",
    )

    second_log = (vault / "wiki" / "log.md").read_text(encoding="utf-8")
    lines = second_log.splitlines()
    assert second_log.startswith(first_log)
    assert first.log_entry.text in second_log
    assert len(lines) == 2
    assert " | human_edit | Second | 人工补录" in lines[1]


def test_unified_page_diff_can_be_generated() -> None:
    """页面级 diff 应使用 unified 格式，并标识新增行。"""
    diff = unified_content_diff("# Alpha\nold line\n", "# Alpha\nnew line\n", from_label="a/x", to_label="b/x")
    result = AuditService().page_diff("wiki/alpha.md", "# Alpha\nold line\n", "# Alpha\nnew line\n")

    assert diff.startswith("--- a/x\n+++ b/x\n")
    assert "-old line\n" in diff
    assert "+new line\n" in diff
    assert result.has_changes
    assert result.diff.startswith("--- a/wiki/alpha.md\n+++ b/wiki/alpha.md\n")


def test_push_without_remote_returns_git_failed_with_nonempty_stderr(tmp_path: Path) -> None:
    """无远端时手动同步返回 E_GIT_FAILED，且 details.stderr 非空。"""
    vault = tmp_path / "vault"
    page = write_page(vault, "alpha.md", "# Alpha\n")
    git_ops = GitOperations()
    AuditLogger(vault).append("compile", ["Alpha"], "初始化")

    git_ops.commit_task(
        vault_path=vault,
        operation_type="compile",
        affected_files=[page],
        reason="初始化",
    )

    with pytest.raises(AppError) as exc_info:
        git_ops.push(vault_path=vault, remote_name="origin")

    assert exc_info.value.code is ErrorCode.GIT_FAILED
    assert exc_info.value.details["stderr"]


def test_local_commit_does_not_require_remote(tmp_path: Path) -> None:
    """仓库没有远端时本地自动 commit 仍必须成功。"""
    vault = tmp_path / "vault"
    page = write_page(vault, "alpha.md", "# Alpha\n")
    service = AuditService()

    result = service.record_task_completion(
        vault_path=vault,
        operation_type="ingest",
        affected_pages=["Alpha"],
        affected_files=[page],
        reason="无远端本地提交",
    )

    assert result.commit.branch
    assert result.commit.affected_file_count == 1
    assert "task=ingest; affected_files=1" in result.commit.message
