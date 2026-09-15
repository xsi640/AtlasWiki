"""TASK-011 素材 CRUD 服务层测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from llmwiki.errors import AppError, ErrorCode
from llmwiki.ingest.service import SourceService
from llmwiki.workspace.store import WikiStore


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    return WikiStore(tmp_path / "vault", initialized=True).initialize()


def write_material(
    vault: Path,
    source_id: str,
    *,
    kind: str = "note",
    status: str = "normal",
    content: str = "原始内容",
    title: str | None = None,
) -> Path:
    store = WikiStore(vault)
    material_title = title or f"素材 {source_id}"
    return store.write_markdown(
        Path("raw") / f"{source_id}.md",
        {
            "id": source_id,
            "title": material_title,
            "kind": kind,
            "status": status,
            "source_url": None if kind == "note" else "https://example.com",
            "tags": ["test"],
            "note": "旧备注",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "raw_meta": {"origin": "test"},
        },
        content,
        update_timestamp=True,
    ).relative_path


def write_derived_page(vault: Path, source_id: str, name: str) -> None:
    store = WikiStore(vault)
    store.write_markdown(
        Path("wiki") / "concepts" / f"{name}.md",
        {
            "title": name,
            "type": "concept",
            "source_type": "compiled",
            "zone": "general",
            "links": [],
            "human_edited": False,
            "status": "active",
            "origin_source": source_id,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        },
        f"[[{name}]] 派生内容\n",
        update_timestamp=True,
    )


async def test_list_supports_filter_counts_and_pagination(vault: Path) -> None:
    write_material(vault, "aaaaaaaaaaaa", status="normal")
    write_material(vault, "bbbbbbbbbbbb", kind="web", status="stale")
    write_material(vault, "cccccccccccc", kind="pdf", status="deleted")
    write_material(vault, "dddddddddddd", status="failed")
    write_derived_page(vault, "bbbbbbbbbbbb", "Web Derived")

    result = await SourceService().list_sources(vault, page=1, size=2)
    assert result["total"] == 4
    assert len(result["items"]) == 2
    assert result["counts"] == {"normal": 1, "failed": 1, "deleted": 1, "stale": 1}

    stale = await SourceService().list_sources(vault, status="stale")
    assert stale["total"] == 1
    assert stale["items"][0]["id"] == "bbbbbbbbbbbb"
    assert stale["items"][0]["derived_page_count"] == 1

    second = await SourceService().list_sources(vault, page=2, size=2)
    assert len(second["items"]) == 2

    with pytest.raises(AppError) as exc:
        await SourceService().list_sources(vault, status="unknown", page=0, size=201)
    assert exc.value.code is ErrorCode.VALIDATION


async def test_get_source_returns_detail_and_derived_pages(vault: Path) -> None:
    write_material(vault, "aaaaaaaaaaaa", kind="note")
    write_derived_page(vault, "aaaaaaaaaaaa", "Derived")

    detail = await SourceService().get_source(vault, "aaaaaaaaaaaa")
    assert detail["id"] == "aaaaaaaaaaaa"
    assert detail["kind"] == "note"
    assert detail["content"] == "原始内容"
    assert detail["content_editable"] is True
    assert detail["derived_pages"] == [
        {"name": "Derived", "title": "Derived", "status": "active"}
    ]

    with pytest.raises(AppError) as exc:
        await SourceService().get_source(vault, "bbbbbbbbbbbb")
    assert exc.value.code is ErrorCode.NOT_FOUND


async def test_update_note_content_and_metadata_sets_stale(vault: Path) -> None:
    write_material(vault, "aaaaaaaaaaaa")
    write_derived_page(vault, "aaaaaaaaaaaa", "Derived")
    before = (vault / "wiki" / "concepts" / "Derived.md").read_text("utf-8")

    result = await SourceService().update_source(
        vault,
        "aaaaaaaaaaaa",
        {"title": "新标题", "content": "新正文", "tags": ["new"], "note": "新备注"},
    )
    assert result["status"] == "stale"
    assert result["needs_recompile"] is True
    assert result["content"] == "新正文"
    assert result["title"] == "新标题"
    assert result["tags"] == ["new"]
    assert (vault / "wiki" / "concepts" / "Derived.md").read_text("utf-8") == before


async def test_web_pdf_content_is_not_editable(vault: Path) -> None:
    path = write_material(vault, "aaaaaaaaaaaa", kind="web", content="外部正文")

    with pytest.raises(AppError) as exc:
        await SourceService().update_source(
            vault,
            "aaaaaaaaaaaa",
            {"content": "尝试修改", "title": "元数据可改"},
        )
    assert exc.value.code is ErrorCode.VALIDATION
    assert exc.value.details["fields"] == {"content": "web/pdf 正文不可编辑"}
    document = WikiStore(vault).read_markdown(path)
    assert document.content == "外部正文"
    assert document.metadata["title"] != "元数据可改"

    with pytest.raises(AppError) as exc:
        await SourceService().update_source(vault, "aaaaaaaaaaaa", {"author": "Ada"})
    assert exc.value.code is ErrorCode.VALIDATION
    assert exc.value.details["fields"] == ["author"]

    updated = await SourceService().update_source(vault, "aaaaaaaaaaaa", {"title": "仅元数据"})
    assert updated["status"] == "stale"
    assert updated["content"] == "外部正文"


async def test_soft_delete_keeps_file_and_restore(vault: Path) -> None:
    write_material(vault, "aaaaaaaaaaaa")
    write_derived_page(vault, "aaaaaaaaaaaa", "Derived")
    service = SourceService()

    deleted = await service.delete_source(vault, "aaaaaaaaaaaa")
    assert deleted["status"] == "deleted"
    assert deleted["affected_page_count"] == 1
    assert deleted["affected_pages"] == ["Derived"]
    assert (vault / "raw" / "aaaaaaaaaaaa.md").is_file()
    assert (vault / "wiki" / "log.md").is_file()

    deleted_list = await service.list_sources(vault, status="deleted")
    normal_list = await service.list_sources(vault, status="normal")
    assert deleted_list["total"] == 1
    assert normal_list["total"] == 0

    restored = await service.restore_source(vault, "aaaaaaaaaaaa")
    assert restored["status"] == "normal"
    normal_after = await service.list_sources(vault, status="normal")
    assert normal_after["total"] == 1

    with pytest.raises(AppError) as exc:
        await service.restore_source(vault, "aaaaaaaaaaaa")
    assert exc.value.code is ErrorCode.VALIDATION


async def test_active_compile_job_blocks_update_and_delete(vault: Path) -> None:
    write_material(vault, "aaaaaaaaaaaa")
    jobs_file = vault / ".llmwiki" / "jobs.json"
    jobs_file.parent.mkdir(parents=True, exist_ok=True)
    jobs_file.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "job-1",
                        "kind": "compile:aaaaaaaaaaaa",
                        "status": "running",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    service = SourceService()

    detail = await service.get_source(vault, "aaaaaaaaaaaa")
    assert detail["content_editable"] is False

    for operation in (
        service.update_source(vault, "aaaaaaaaaaaa", {"title": "busy"}),
        service.delete_source(vault, "aaaaaaaaaaaa"),
    ):
        with pytest.raises(AppError) as exc:
            await operation
        assert exc.value.code is ErrorCode.SOURCE_BUSY
