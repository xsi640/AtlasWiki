"""TASK-026 / TASK-027 问答引擎与 API 验收测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from llmwiki.api import ask as ask_api
from llmwiki.ask import AskEngine
from llmwiki.config import ConfigStore, LlmSettings, Settings
from llmwiki.errors import AppError, ErrorCode
from llmwiki.jobs import Job, JobQueue
from llmwiki.main import app
from llmwiki.workspace.store import PageDraft, WikiStore


@dataclass
class MockLlm:
    output: str
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def complete(
        self, messages: list[dict[str, str]], *, json_mode: bool, job_id: str | None = None
    ) -> str:
        self.requests.append({"messages": messages, "json_mode": json_mode, "job_id": job_id})
        return self.output


def make_config(tmp_path: Path, vault: Path, *, api_key: str = "mock-key") -> ConfigStore:
    config = ConfigStore(tmp_path / "config")
    config.save(
        Settings(
            vault_path=str(vault),
            llm=LlmSettings(api_key=api_key, base_url="https://llm.example/v1"),
        )
    )
    return config


def write_page(store: WikiStore, name: str, title: str, content: str) -> None:
    store.write_page(
        PageDraft(
            name=name,
            title=title,
            page_type="concept",
            source_type="compiled",
            zone="测试",
            content=content,
        )
    )


def sufficient_output() -> str:
    return json.dumps(
        {
            "answer": "Raft 通过多数派确认达成共识，详见 [[Raft]]。",
            "sufficient": True,
            "related_pages": [{"name": "Paxos", "title": "Paxos"}],
        },
        ensure_ascii=False,
    )


def insufficient_output() -> str:
    return json.dumps(
        {
            "answer": "资料不够。",
            "sufficient": False,
            "related_pages": [{"name": "Raft", "title": "Raft"}],
        },
        ensure_ascii=False,
    )


async def run_ask(
    tmp_path: Path, output: str, question: str = "Raft 如何达成共识？"
) -> tuple[dict, Path, MockLlm]:
    vault = tmp_path / "vault"
    store = WikiStore(vault, initialized=True)
    write_page(store, "Raft", "Raft", "Raft 需要多数派确认。")
    write_page(store, "Paxos", "Paxos", "Paxos 是另一种共识算法。")
    write_page(store, "Other", "Other", "完全无关内容。")
    llm = MockLlm(output)
    engine = AskEngine(llm_client=llm, config_store_override=make_config(tmp_path, vault))
    record = await engine.ask(Job(), vault, question)
    return record, vault, llm


async def test_ask_selects_pages_and_records_replay(tmp_path: Path) -> None:
    record, vault, llm = await run_ask(tmp_path, sufficient_output())

    assert record["sufficient"] is True
    assert record["pages_considered"] == 2
    assert [item["page"] for item in record["citations"]] == ["Raft"]
    assert record["citations"][0]["title"] == "Raft"
    assert record["related_pages"][0]["name"] == "Paxos"
    assert record["cost"]["currency"] == "USD"
    assert record["saved_page"] is None
    assert llm.requests[0]["json_mode"] is True
    assert "[[Raft]]" in llm.requests[0]["messages"][0]["content"]

    replay = json.loads((vault / ".llmwiki" / "queries.json").read_text("utf-8"))
    assert replay == [record]


async def test_insufficient_answer_has_related_pages(tmp_path: Path) -> None:
    record, _vault, _llm = await run_ask(
        tmp_path, insufficient_output(), question="完全不存在的主题"
    )

    assert record["sufficient"] is False
    assert "知识不足" in record["answer"]
    assert len(record["related_pages"]) <= 5
    assert all(item["name"] in {"Raft", "Paxos", "Other"} for item in record["related_pages"])
    assert record["pages_considered"] <= 10


async def test_missing_api_key_raises_not_configured(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    WikiStore(vault, initialized=True)
    engine = AskEngine(
        llm_client=MockLlm(sufficient_output()),
        config_store_override=make_config(tmp_path, vault, api_key=""),
    )
    with pytest.raises(AppError) as exc_info:
        await engine.ask(Job(), vault, "任意问题")
    assert exc_info.value.code is ErrorCode.LLM_NOT_CONFIGURED


def configure_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_key: str = "mock-key",
) -> tuple[Path, JobQueue]:
    vault = tmp_path / "api-vault"
    store = WikiStore(vault, initialized=True)
    write_page(store, "Raft", "Raft", "Raft 需要多数派确认。")
    config = make_config(tmp_path / "api", vault, api_key=api_key)
    queue = JobQueue(config_store_override=config)
    monkeypatch.setattr(ask_api, "config_store", config)
    monkeypatch.setattr(ask_api, "job_queue", queue)
    return vault, queue


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """隔离 API 依赖并注入 mock LLM。"""

    def factory(output: str):
        vault, queue = configure_api(tmp_path, monkeypatch)
        engine = AskEngine(
            llm_client=MockLlm(output),
            config_store_override=queue.config_store,
        )
        monkeypatch.setattr(ask_api, "AskEngine", lambda: engine)
        return TestClient(app), vault, queue

    return factory


def test_ask_api_lifecycle(api_client, tmp_path: Path) -> None:
    client, vault, _queue = api_client(sufficient_output())
    with client:
        response = client.post("/api/ask", json={"question": "Raft 如何达成共识？"})
        assert response.status_code == 200
        record = response.json()
        query_id = record["id"]
        assert record["pages_considered"] == 1

        listing = client.get("/api/queries").json()
        assert listing["total"] == 1
        assert listing["items"][0]["id"] == query_id
        assert client.get(f"/api/queries/{query_id}").json() == record

        first_save = client.post(f"/api/ask/{query_id}/save-as-page", json={"zone": "问答"})
        assert first_save.status_code == 200
        page_name = first_save.json()["page"]["name"]
        second_save = client.post(f"/api/ask/{query_id}/save-as-page")
        assert second_save.json()["page"]["name"] == page_name

        page = WikiStore(vault).read_page(page_name)
        assert page.metadata["source_type"] == "query-generated"
        assert page.metadata["type"] == "analysis"
        assert page.relative_path.as_posix().startswith("wiki/analyses/")
        assert len(WikiStore(vault).list_page_names()) == 2
        assert client.get(f"/api/queries/{query_id}").json()["saved_page"]["name"] == page_name

        assert client.delete(f"/api/queries/{query_id}").status_code == 200
        assert client.get("/api/queries").json() == {"items": [], "total": 0}
        assert client.get(f"/api/queries/{query_id}").status_code == 404


def test_ask_api_requires_key(api_client) -> None:
    client, _vault, _queue = api_client(sufficient_output())
    # 直接修改模块级 config 缓存中的 key。
    ask_api.config_store.load().llm.api_key = ""
    response = client.post("/api/ask", json={"question": "任意问题"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == ErrorCode.LLM_NOT_CONFIGURED.value
