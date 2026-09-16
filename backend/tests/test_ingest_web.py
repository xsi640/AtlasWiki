"""TASK-008：网页素材解析器测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlaswiki.config import Settings, config_store
from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.ingest.web import fetch_web
from atlaswiki.schema import MaterialKind, MaterialStatus

_SAMPLE_HTML = """\
<html>
<head><title>Understanding AtlasWiki</title></head>
<body>
<article>
<h1>Understanding AtlasWiki</h1>
<p>AtlasWiki is a new approach to knowledge management that compiles raw material into interconnected markdown pages at ingest time, unlike traditional RAG which retrieves at query time.</p>
<p>This approach allows knowledge to compound over time as the wiki grows.</p>
</article>
</body>
</html>
"""


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "vault"
    monkeypatch.setattr(config_store, "_cache", Settings(vault_path=str(root)))
    return root


async def test_fetch_web_extracts_and_stores_content(vault: Path) -> None:
    result = await fetch_web(
        "https://example.com/llm-wiki",
        fetched_html=_SAMPLE_HTML,
        tags=["知识管理"],
    )
    assert result["kind"] == MaterialKind.WEB.value
    assert result["status"] == MaterialStatus.NORMAL.value
    assert result["source_url"] == "https://example.com/llm-wiki"
    assert result["tags"] == ["知识管理"]
    assert len(result["content"]) > 10


async def test_fetch_web_rejects_duplicate_content(vault: Path) -> None:
    first = await fetch_web("https://example.com/post", fetched_html=_SAMPLE_HTML)
    with pytest.raises(AppError) as raised:
        await fetch_web("https://example.com/post", fetched_html=_SAMPLE_HTML)
    assert raised.value.code is ErrorCode.DUPLICATE_SOURCE
    assert raised.value.details["existing"]["id"] == first["id"]


async def test_fetch_web_rejects_empty_url(vault: Path) -> None:
    with pytest.raises(AppError) as raised:
        await fetch_web("")
    assert raised.value.code is ErrorCode.VALIDATION


async def test_fetch_web_rejects_invalid_url_scheme(vault: Path) -> None:
    with pytest.raises(AppError) as raised:
        await fetch_web("ftp://example.com/file")
    assert raised.value.code is ErrorCode.VALIDATION


async def test_fetch_web_empty_extraction_raises_parse_failed(vault: Path) -> None:
    html = "<html><body></body></html>"
    with pytest.raises((AppError, ValueError)):
        await fetch_web("https://example.com/empty", fetched_html=html)
