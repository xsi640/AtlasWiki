"""vault 独立 git 仓库的提交、推送与 diff 操作。"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from atlaswiki.config import config_store
from atlaswiki.errors import AppError, ErrorCode

from .log import LOG_RELATIVE_PATH

GIT_TIMEOUT_S = 30


@dataclass(frozen=True)
class GitCommandResult:
    """git 子进程输出。"""

    args: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class GitCommitResult:
    """一次写入任务审计提交的结果。"""

    commit_hash: str
    branch: str
    message: str
    affected_file_count: int
    changed_files: tuple[str, ...]
    pushed: bool = False


class GitOperations:
    """用 git CLI 实现 vault 级自动提交与手动同步。"""

    def _resolve_vault(self, vault_path: Path | str | None) -> Path:
        """优先使用显式 vault；测试和同进程多 vault 场景不依赖全局状态。"""
        raw_path = vault_path if vault_path is not None else config_store.load().vault_path
        if not raw_path:
            raise AppError(ErrorCode.VALIDATION, "尚未配置 vault_path")
        return Path(raw_path).expanduser().resolve()

    def _git(
        self,
        vault_path: Path,
        args: Sequence[str],
        *,
        check: bool = False,
        timeout: int = GIT_TIMEOUT_S,
    ) -> GitCommandResult:
        """执行 git 命令，失败时统一转成 `E_GIT_FAILED`。"""
        argv = ["git", *args]
        try:
            process = subprocess.run(
                argv,
                cwd=vault_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            stderr = f"无法执行 {' '.join(argv)}: {exc}"
            raise AppError(ErrorCode.GIT_FAILED, "git 命令执行失败", {"stderr": stderr}) from exc

        result = GitCommandResult(
            args=tuple(args),
            stdout=process.stdout,
            stderr=process.stderr,
            returncode=process.returncode,
        )
        if check and process.returncode != 0:
            message = process.stderr.strip() or process.stdout.strip() or f"git {args[0]} 失败"
            raise AppError(ErrorCode.GIT_FAILED, message, {"stderr": result.stderr or message})
        return result

    def ensure_repository(self, vault_path: Path | str | None = None) -> Path:
        """确保 vault 自身是 git 仓库；只有缺少本地 `.git` 时才初始化。"""
        vault = self._resolve_vault(vault_path)
        vault.mkdir(parents=True, exist_ok=True)
        if not (vault / ".git").exists():
            self._git(vault, ["init"], check=True)
        return vault

    @staticmethod
    def _relative_to_vault(vault: Path, affected_file: Path | str) -> str:
        """把调用方提供的任务文件转换为安全相对 pathspec。"""
        path = Path(affected_file)
        absolute = path.resolve() if path.is_absolute() else (vault / path).resolve()
        if not absolute.is_relative_to(vault):
            raise AppError(
                ErrorCode.GIT_FAILED,
                "受影响文件不在 vault 内",
                {"stderr": "one or more affected files are outside the vault"},
            )
        return absolute.relative_to(vault).as_posix()

    def commit_task(
        self,
        *,
        operation_type: str,
        affected_files: Sequence[Path | str],
        vault_path: Path | str | None = None,
        reason: str = "",
    ) -> GitCommitResult:
        """提交一次写入任务的受影响文件与 `wiki/log.md`。"""
        if not affected_files:
            raise AppError(
                ErrorCode.GIT_FAILED,
                "写入任务必须声明受影响文件",
                {"stderr": "affected_files is empty"},
            )

        vault = self.ensure_repository(vault_path)
        relative_files = [self._relative_to_vault(vault, item) for item in affected_files]
        pathspecs = [*relative_files, LOG_RELATIVE_PATH.as_posix()]
        self._git(vault, ["add", "--", *pathspecs], check=True)

        status = self._git(vault, ["diff", "--cached", "--name-only", "-z"])
        changed_files = tuple(name for name in status.stdout.split("\0") if name)
        if not changed_files:
            raise AppError(
                ErrorCode.GIT_FAILED,
                "没有可提交的文件变更",
                {"stderr": "no staged changes"},
            )

        safe_operation = " ".join(operation_type.split())
        message = f"task={safe_operation}; affected_files={len(relative_files)}"
        if reason:
            message = f"{message}; reason={' '.join(reason.split())}"

        # 显式本仓库身份，避免新机器缺少 git 全局配置导致自动提交失败。
        self._git(
            vault,
            [
                "-c",
                "user.name=AtlasWiki",
                "-c",
                "user.email=atlaswiki@local",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-m",
                message,
            ],
            check=True,
        )
        commit_hash = self._git(vault, ["rev-parse", "HEAD"], check=True).stdout.strip()
        branch = self._git(vault, ["branch", "--show-current"], check=True).stdout.strip() or "HEAD"
        return GitCommitResult(
            commit_hash=commit_hash,
            branch=branch,
            message=message,
            affected_file_count=len(relative_files),
            changed_files=changed_files,
        )

    def current_branch(self, vault_path: Path | str | None = None) -> str:
        """返回当前分支；detached HEAD 时返回 `HEAD`。"""
        vault = self.ensure_repository(vault_path)
        return self._git(vault, ["branch", "--show-current"], check=True).stdout.strip() or "HEAD"

    def has_remote(self, remote_name: str, vault_path: Path | str | None = None) -> bool:
        """判断指定远端是否已配置。"""
        vault = self.ensure_repository(vault_path)
        result = self._git(vault, ["config", "--get", f"remote.{remote_name}.url"])
        return result.returncode == 0 and bool(result.stdout.strip())

    def push(
        self,
        *,
        remote_name: str = "origin",
        vault_path: Path | str | None = None,
        branch: str | None = None,
    ) -> GitCommandResult:
        """推送当前分支；无远端时抛出带非空 stderr 的业务错误。"""
        vault = self.ensure_repository(vault_path)
        if not self.has_remote(remote_name, vault):
            stderr = f"remote '{remote_name}' is not configured"
            raise AppError(ErrorCode.GIT_FAILED, "git 远端未配置", {"stderr": stderr})

        target_branch = branch or self.current_branch(vault)
        result = self._git(vault, ["push", remote_name, target_branch])
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "git push 失败"
            raise AppError(ErrorCode.GIT_FAILED, "git push 失败", {"stderr": stderr})
        return result

    def sync(
        self,
        *,
        vault_path: Path | str | None = None,
        remote_name: str | None = None,
    ) -> GitCommandResult:
        """设置页手动同步入口；远端名缺省读取配置。"""
        settings = config_store.load()
        return self.push(
            remote_name=remote_name or settings.git.remote_name,
            vault_path=vault_path,
        )

    def diff(
        self,
        *,
        vault_path: Path | str | None = None,
        affected_files: Sequence[Path | str] | None = None,
        from_revision: str = "HEAD~1",
        to_revision: str = "HEAD",
        context_lines: int = 3,
    ) -> str:
        """获取仓库、指定文件或页面在两个 git 版本间的 unified diff。"""
        vault = self.ensure_repository(vault_path)
        args = ["diff", f"--unified={context_lines}", from_revision, to_revision]
        if affected_files:
            pathspecs = [self._relative_to_vault(vault, item) for item in affected_files]
            args.extend(["--", *pathspecs])
        result = self._git(vault, args)
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip() or "git diff 失败"
            raise AppError(ErrorCode.GIT_FAILED, "git diff 失败", {"stderr": stderr})
        return result.stdout
