"""TASK-003：Wiki 存储与链接层验收测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

import atlaswiki.workspace.store as store_module
from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.workspace import (
    VAULT_DIRECTORIES,
    PageDraft,
    WikiStore,
    create_vault,
    extract_links,
    safe_relative_path,
)


def test_create_vault_skeleton(tmp_path: Path) -> None:
    vault = create_vault(tmp_path / "knowledge")

    assert vault.is_dir()
    for directory in VAULT_DIRECTORIES:
        assert (vault / directory).is_dir()


def test_frontmatter_roundtrip_with_chinese_and_lists(tmp_path: Path) -> None:
    store = WikiStore(tmp_path)
    store.initialize()
    metadata = {
        "title": "分布式知识库",
        "type": "concept",
        "source_type": "compiled",
        "zone": "知识管理",
        "links": ["增量维护", "索引设计", "GraphRAG"],
        "human_edited": True,
        "status": "active",
    }
    content = "# 中文标题\n\n保留数组与多行内容。"

    store.write_markdown("wiki/concepts/分布式知识库.md", metadata, content)
    loaded = store.read_markdown("wiki/concepts/分布式知识库.md")

    assert loaded.metadata == metadata
    assert loaded.content == content


def test_extract_links_with_aliases_and_positions() -> None:
    links = extract_links("见 [[增量维护|如何增量维护]] 与 [[索引设计]]。")

    assert [link.target for link in links] == ["增量维护", "索引设计"]
    assert [link.label for link in links] == ["如何增量维护", "索引设计"]
    assert links[0].line == 1
    assert links[0].column == 3


def test_five_pages_and_eight_edges_link_index(tmp_path: Path) -> None:
    store = WikiStore(tmp_path, initialized=True)
    edges = {
        "页面A": ["页面B", "页面C", "页面D"],
        "页面B": ["页面A", "页面C"],
        "页面C": ["页面D", "页面A"],
        "页面D": ["页面E"],
        "页面E": [],
    }
    for source, targets in edges.items():
        content = " ".join(f"[[{target}]]" for target in targets)
        store.write_page(
            PageDraft(
                name=source,
                title=source,
                page_type="concept",
                source_type="compiled",
                zone="测试",
                content=content,
            )
        )

    index = store.link_index()

    assert index.nodes == tuple(sorted(edges))
    assert index.out_links == edges
    expected_backlinks = {
        "页面A": ["页面B", "页面C"],
        "页面B": ["页面A"],
        "页面C": ["页面A", "页面B"],
        "页面D": ["页面A", "页面C"],
        "页面E": ["页面D"],
    }
    assert index.back_links == expected_backlinks
    assert set(index.edges) == {
        ("页面A", "页面B"),
        ("页面A", "页面C"),
        ("页面A", "页面D"),
        ("页面B", "页面A"),
        ("页面B", "页面C"),
        ("页面C", "页面D"),
        ("页面C", "页面A"),
        ("页面D", "页面E"),
    }
    assert len(index.edges) == 8
    assert store.back_links("页面D") == ["页面A", "页面C"]
    assert store.out_links("页面A") == ["页面B", "页面C", "页面D"]


def test_atomic_write_interrupt_keeps_old_target(tmp_path: Path) -> None:
    store = WikiStore(tmp_path, initialized=True)
    path = "wiki/concepts/原子写.md"
    store.write_markdown(path, {"title": "old"}, "old content")
    target = tmp_path / path

    original_replace = store_module.os.replace

    def interrupted_replace(src: Path, dst: Path) -> None:
        raise KeyboardInterrupt

    store_module.os.replace = interrupted_replace
    try:
        with pytest.raises(KeyboardInterrupt):
            store.write_markdown(path, {"title": "new"}, "new content")
    finally:
        store_module.os.replace = original_replace

    assert target.read_text(encoding="utf-8") == "---\ntitle: old\n---\n\nold content"
    assert not list(target.parent.glob(".*.tmp"))


@pytest.mark.parametrize(
    "path",
    [
        "../outside.md",
        "a/../../outside.md",
        "/etc/passwd",
        "C:\\outside.md",
        "C:/outside.md",
        "C:outside.md",
        "\\\\server\\share\\page.md",
    ],
)
def test_reject_illegal_paths(path: str) -> None:
    with pytest.raises(AppError) as exc_info:
        safe_relative_path(path)

    assert exc_info.value.code == ErrorCode.PATH_OUT_OF_VAULT
