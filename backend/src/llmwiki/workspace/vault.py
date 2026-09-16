"""Vault 目录布局与路径安全（MODULE-003）。"""

from __future__ import annotations

from pathlib import Path

from llmwiki.errors import AppError, ErrorCode

# 目录布局来自 tech-architecture.md §5.1。
VAULT_DIRECTORIES: tuple[str, ...] = (
    "raw/assets",
    "wiki/sources",
    "wiki/concepts",
    "wiki/entities",
    "wiki/analyses",
    ".llmwiki",
)

def safe_relative_path(raw: str | Path) -> Path:
    """校验并返回 vault 内相对路径；非法输入统一抛 PATH_OUT_OF_VAULT。"""

    value = str(raw)
    if not value.strip() or "\x00" in value:
        raise AppError(
            ErrorCode.PATH_OUT_OF_VAULT,
            "路径不能为空或包含空字节",
            {"path": value},
        )

    path = Path(value)
    # Path.drive 在 POSIX 上不识别 Windows 盘符，因此补充显式校验。
    has_windows_drive = len(value) >= 2 and value[0].isascii() and value[0].isalpha() and value[1] == ":"
    if (
        path.is_absolute()
        or bool(path.drive)
        or bool(path.root)
        or has_windows_drive
        or value.startswith("\\\\")
        or ".." in path.parts
    ):
        raise AppError(
            ErrorCode.PATH_OUT_OF_VAULT,
            "只允许 vault 内相对路径",
            {"path": value},
        )
    return path


def ensure_inside_vault(vault: str | Path, relative_path: str | Path) -> Path:
    """归一化路径，并确保它仍在 vault 内。"""

    root = Path(vault).expanduser().resolve()
    candidate = safe_relative_path(relative_path)
    normalized = (root / candidate).resolve(strict=False)
    try:
        normalized.relative_to(root)
    except ValueError as exc:
        raise AppError(
            ErrorCode.PATH_OUT_OF_VAULT,
            "路径越界：目标不在 vault 内",
            {"path": str(relative_path)},
        ) from exc
    return normalized


def create_vault(vault: str | Path) -> Path:
    """创建 vault 骨架目录；重复调用是幂等的。"""

    root = Path(vault).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise AppError(ErrorCode.VALIDATION, "vault 路径已存在且不是目录", {"path": str(root)})

    for directory in VAULT_DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)
    return root
