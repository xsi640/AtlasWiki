"""TASK-010：手写笔记解析器验收测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter
import pytest

from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.ingest.note import import_note


class _StubConfigStore:
    """避免测试写入真实用户配置目录。"""

    def __init__(self, vault_path: Path) -> None:
        self._vault_path = vault_path

    def load(self) -> Any:
        class _Settings:
            vault_path = str(self._vault_path)

        return _Settings()


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把冻结配置指向临时 vault。"""

    import atlaswiki.workspace.store as store_module

    path = tmp_path / "vault"
    monkeypatch.setattr(store_module, "config_store", _StubConfigStore(path))
    return path


async def test_import_note_writes_raw_material(vault: Path) -> None:
    result = await import_note("  手写笔记  ", "# 第一段\n\n保留原始换行。")

    assert result["title"] == "手写笔记"
    assert result["kind"] == "note"
    assert result["source_url"] is None
    assert result["status"] == "normal"
    assert result["tags"] == []
    assert result["content_editable"] is True
    assert result["created_at"]
    assert result["content"] == "# 第一段\n\n保留原始换行。"

    material_path = vault / result["path"]
    assert material_path.is_file()
    assert material_path.parent == vault / "raw"

    post = frontmatter.loads(material_path.read_text(encoding="utf-8"))
    assert post.metadata["title"] == "手写笔记"
    assert post.metadata["kind"] == "note"
    assert post.metadata["source_url"] is None
    assert post.metadata["status"] == "normal"
    assert post.metadata["tags"] == []
    assert post.metadata["content_editable"] is True
    assert post.content == "# 第一段\n\n保留原始换行。"


async def test_import_note_with_tags(vault: Path) -> None:
    result = await import_note("标签笔记", "正文", tags=[" 知识管理 ", "LLM"])

    assert result["tags"] == ["知识管理", "LLM"]

    post = frontmatter.loads((vault / result["path"]).read_text(encoding="utf-8"))
    assert post.metadata["tags"] == ["知识管理", "LLM"]


async def test_import_note_rejects_empty_title(vault: Path) -> None:
    with pytest.raises(AppError) as exc_info:
        await import_note("   ", "正文")

    error = exc_info.value
    assert error.code == ErrorCode.VALIDATION
    assert error.details["fields"]["title"]
    assert "content" not in error.details["fields"]
    assert not (vault / "raw").exists()


async def test_import_note_rejects_empty_content(vault: Path) -> None:
    with pytest.raises(AppError) as exc_info:
        await import_note("标题", " \n\t ")

    error = exc_info.value
    assert error.code == ErrorCode.VALIDATION
    assert error.details["fields"]["content"]
    assert "title" not in error.details["fields"]
    assert not (vault / "raw").exists()
