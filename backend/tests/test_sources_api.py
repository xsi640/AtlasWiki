"""TASK-012：素材 API 接口层验收测试（API-014 ~ API-023）。"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from atlaswiki.api import sources as sources_api
from atlaswiki.config import LlmSettings, Settings, config_store
from atlaswiki.jobs import JobQueue
from atlaswiki.main import app
from atlaswiki.workspace.store import WikiStore


@dataclass
class MockAudit:
    """避免测试依赖本机 git 身份与远端。"""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def record_task_completion(self, **payload: Any) -> dict[str, Any]:
        self.calls.append(payload)
        return {"ok": True}


def install_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """隔离全局配置并返回 (vault, 配置目录)。"""

    vault = tmp_path / "vault"
    config_dir = tmp_path / "app-config"
    monkeypatch.setattr(
        config_store,
        "_cache",
        Settings(
            vault_path=str(vault),
            llm=LlmSettings(api_key="mock-key", base_url="https://llm.example/v1"),
        ),
    )
    monkeypatch.setattr(config_store, "_dir", config_dir)
    monkeypatch.setattr(config_store, "_path", config_dir / "settings.json")
    return vault, config_dir


def fresh_queue(monkeypatch: pytest.MonkeyPatch) -> JobQueue:
    """替换全局任务队列，避免用例间共享内存状态。"""

    queue = JobQueue(config_store_override=config_store)
    monkeypatch.setattr(sources_api, "job_queue", queue)
    return queue


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    install_config(tmp_path, monkeypatch)
    fresh_queue(monkeypatch)
    return TestClient(app)


def write_note_raw(vault: Path, *, source_id: str, title: str, content: str, kind: str = "note") -> None:
    store = WikiStore(vault, initialized=True)
    store.write_markdown(
        f"raw/{title}-{source_id}.md",
        {
            "id": source_id,
            "title": title,
            "kind": kind,
            "source_url": f"https://example.com/{source_id}" if kind == "web" else None,
            "status": "normal",
            "tags": [],
        },
        content,
    )


# ---------------------------------------------------------------------------
# API-014 列表
# ---------------------------------------------------------------------------


def test_source_list_counts_and_filters(client: TestClient, tmp_path: Path) -> None:
    vault = Path(config_store.load().vault_path)
    write_note_raw(vault, source_id="aaaaaaaaaaaa", title="正常笔记", content="正文")
    write_note_raw(vault, source_id="bbbbbbbbbbbb", title="旧笔记", content="正文")

    # 把第二篇置为 stale。
    store = WikiStore(vault)
    document = store.read_markdown("raw/旧笔记-bbbbbbbbbbbb.md")
    metadata = {**document.metadata, "status": "stale"}
    store.write_markdown("raw/旧笔记-bbbbbbbbbbbb.md", metadata, document.content)

    response = client.get("/api/sources")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["counts"] == {"normal": 1, "failed": 0, "deleted": 0, "stale": 1}

    stale_only = client.get("/api/sources", params={"status": "stale"})
    assert [item["id"] for item in stale_only.json()["items"]] == ["bbbbbbbbbbbb"]

    multi = client.get("/api/sources", params={"status": "stale,failed"})
    assert multi.json()["total"] == 1

    invalid = client.get("/api/sources", params={"status": "bogus"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "E_VALIDATION"

    oversize = client.get("/api/sources", params={"size": 500})
    assert oversize.status_code == 422


def test_source_list_requires_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_config(tmp_path, monkeypatch)
    fresh_queue(monkeypatch)
    monkeypatch.setattr(config_store, "_cache", Settings(vault_path=""))
    client = TestClient(app)

    response = client.get("/api/sources")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E_VALIDATION"


# ---------------------------------------------------------------------------
# API-016 笔记导入 + API-019 编辑 + API-020/021 删除恢复
# ---------------------------------------------------------------------------


def test_note_import_edit_delete_restore_roundtrip(client: TestClient) -> None:
    imported = client.post(
        "/api/sources/note",
        json={"title": "编译笔记", "content": "编译器把素材变成 wiki 页面。", "tags": ["编译"]},
    )
    assert imported.status_code == 200
    detail = imported.json()
    source_id = detail["id"]
    assert detail["kind"] == "note"
    assert detail["status"] == "normal"
    assert detail["content_editable"] is True
    assert detail["content"].startswith("编译器")
    assert detail["derived_pages"] == []

    # API-019：note 可改正文，保存后 stale + needs_recompile。
    edited = client.patch(
        f"/api/sources/{source_id}",
        json={"content": "更新后的正文。", "note": "补充说明"},
    )
    assert edited.status_code == 200
    assert edited.json()["status"] == "stale"
    assert edited.json()["needs_recompile"] is True

    # API-018 详情一致。
    fetched = client.get(f"/api/sources/{source_id}").json()
    assert fetched["content"] == "更新后的正文。"
    assert fetched["note"] == "补充说明"

    # API-020 软删除。
    deleted = client.delete(f"/api/sources/{source_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert deleted.json()["affected_page_count"] == 0

    assert client.get("/api/sources", params={"status": "deleted"}).json()["total"] == 1
    assert client.get("/api/sources", params={"status": "normal"}).json()["total"] == 0

    # API-021 恢复。
    restored = client.post(f"/api/sources/{source_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "normal"

    # 不存在的素材 → 404。
    assert client.get("/api/sources/000000000000").status_code == 404
    # 非法 id → 422。
    assert client.get("/api/sources/not-an-id").status_code == 422


def test_note_import_validates_fields(client: TestClient) -> None:
    missing = client.post("/api/sources/note", json={"title": "", "content": " "})
    assert missing.status_code == 422
    fields = missing.json()["error"]["details"]["fields"]
    reasons = {item["field"] for item in fields} if isinstance(fields, list) else set(fields)
    assert {"title", "content"} <= set(reasons)


def test_import_without_vault_returns_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_config(tmp_path, monkeypatch)
    fresh_queue(monkeypatch)
    monkeypatch.setattr(config_store, "_cache", Settings(vault_path=""))
    client = TestClient(app)

    response = client.post("/api/sources/note", json={"title": "t", "content": "c"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E_VALIDATION"


# ---------------------------------------------------------------------------
# API-015 网页导入（mock 抓取）+ web 正文不可编辑
# ---------------------------------------------------------------------------


def test_web_import_returns_detail_and_protects_content(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = Path(config_store.load().vault_path)

    async def fake_fetch_web(url: str, *, title: str | None = None, tags: list[str] | None = None):
        write_note_raw(vault, source_id="abcdef123456", title=title or "网页", content="网页正文", kind="web")
        return {
            "id": "abcdef123456",
            "title": title or "网页",
            "kind": "web",
            "source_url": url,
            "status": "normal",
            "tags": tags or [],
            "content": "网页正文",
            "content_editable": False,
            "failure_reason": None,
        }

    monkeypatch.setattr(sources_api, "ingest_web", fake_fetch_web)

    imported = client.post(
        "/api/sources/web",
        json={"url": "https://example.com/post", "title": "网页", "tags": ["web"]},
    )
    assert imported.status_code == 200
    detail = imported.json()
    assert detail["kind"] == "web"
    assert detail["content_editable"] is False

    # API-019：web 传 content → E_VALIDATION。
    rejected = client.patch(f"/api/sources/{detail['id']}", json={"content": "改不动"})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "E_VALIDATION"


def test_web_import_requires_url(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def exploding(*_args: Any, **_kwargs: Any) -> dict[str, Any]:  # pragma: no cover
        raise AssertionError("不应触发真实抓取")

    monkeypatch.setattr(sources_api, "ingest_web", exploding)
    response = client.post("/api/sources/web", json={"url": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E_VALIDATION"


# ---------------------------------------------------------------------------
# API-017 PDF 上传 + API-023 原件
# ---------------------------------------------------------------------------


def _minimal_pdf_bytes(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    stream = DecodedStreamObject()
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    stream.set_data(f"BT /F1 18 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = stream
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_pdf_upload_asset_and_download(client: TestClient) -> None:
    imported = client.post(
        "/api/sources/pdf",
        files={"file": ("paper.pdf", _minimal_pdf_bytes("Hello PDF"), "application/pdf")},
        data={"tags": "pdf,测试"},
    )
    assert imported.status_code == 200
    detail = imported.json()
    assert detail["kind"] == "pdf"
    assert detail["status"] == "normal"
    assert detail["asset_path"]
    assert "Hello PDF" in detail["content"]
    assert detail["tags"] == ["pdf", "测试"]

    # API-023：默认返回路径；download=1 返回文件流。
    info = client.get(f"/api/sources/{detail['id']}/asset").json()
    assert info["opened"] is False
    assert info["path"].endswith(".pdf")

    download = client.get(f"/api/sources/{detail['id']}/asset", params={"download": "1"})
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")


def test_pdf_upload_rejects_oversize(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sources_api, "_MAX_UPLOAD_BYTES", 8)
    response = client.post(
        "/api/sources/pdf",
        files={"file": ("big.pdf", b"1234567890", "application/pdf")},
    )
    assert response.status_code == 422
    assert "上限" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# API-022 重编译
# ---------------------------------------------------------------------------


def test_recompile_queues_engine_job(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = Path(config_store.load().vault_path)
    write_note_raw(vault, source_id="cccccccccccc", title="待重编译", content="正文")

    captured: dict[str, Any] = {}

    @dataclass
    class FakeJob:
        id = "job-test-1"

    class FakeEngine:
        def __init__(self, *, queue: Any = None) -> None:
            captured["queue"] = queue

        async def start_compile(self, vault_path: Path, source_ids: list[str]) -> FakeJob:
            captured["vault"] = vault_path
            captured["ids"] = source_ids
            return FakeJob()

    monkeypatch.setattr(sources_api, "CompileEngine", FakeEngine)

    response = client.post("/api/sources/cccccccccccc/recompile")
    assert response.status_code == 200
    assert response.json() == {"job_id": "job-test-1", "queued_sources": 1}
    assert captured["ids"] == ["cccccccccccc"]
