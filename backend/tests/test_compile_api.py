"""TASK-016：编译与变更清单 API 验收测试（API-024 ~ API-027）。"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from atlaswiki.api import compile as compile_api
from atlaswiki.compile import CompileEngine
from atlaswiki.config import LlmSettings, Settings, config_store
from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.jobs import Job, JobQueue
from atlaswiki.main import app
from atlaswiki.workspace.store import WikiStore


@dataclass
class MockLlm:
    """按顺序返回预设输出的 mock 客户端。"""

    outputs: list[str]
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def complete(self, messages: list[dict[str, str]], *, json_mode: bool) -> str:
        self.requests.append({"messages": messages, "json_mode": json_mode})
        return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]


@dataclass
class MockAudit:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def record_task_completion(self, **payload: Any) -> dict[str, Any]:
        self.calls.append(payload)
        return {"ok": True}


def valid_output() -> str:
    return json.dumps(
        {
            "summary_page": {
                "title": "共识算法摘要",
                "zone": "分布式系统",
                "content": "本素材讨论共识算法，重点见 [[Raft]]。",
            },
            "concept_pages": [
                {"title": "Raft", "zone": "分布式系统", "content": "Raft 是共识算法。"}
            ],
            "entity_pages": [],
            "contradictions": [],
        },
        ensure_ascii=False,
    )


def zone_changed_output(zone: str) -> str:
    payload = json.loads(valid_output())
    payload["summary_page"]["zone"] = zone
    payload["concept_pages"][0]["zone"] = zone
    return json.dumps(payload, ensure_ascii=False)


def install_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    outputs: list[str],
    max_cost: float = 1.0,
) -> tuple[TestClient, Path, JobQueue, MockLlm]:
    """隔离配置、队列与编译引擎，返回 (client, vault, queue, mock_llm)。"""

    vault = tmp_path / "vault"
    WikiStore(vault, initialized=True)
    config = Settings(
        vault_path=str(vault),
        llm=LlmSettings(
            api_key="mock-key",
            base_url="https://llm.example/v1",
            max_cost_per_task_usd=max_cost,
        ),
    )
    monkeypatch.setattr(config_store, "_cache", config)
    monkeypatch.setattr(config_store, "_dir", tmp_path / "app-config")
    monkeypatch.setattr(config_store, "_path", tmp_path / "app-config" / "settings.json")

    queue = JobQueue(config_store_override=config_store)
    monkeypatch.setattr(compile_api, "job_queue", queue)

    mock_llm = MockLlm(list(outputs))
    engine = CompileEngine(
        llm=mock_llm,
        audit_service=MockAudit(),
        queue=queue,
        config_store_override=config_store,
    )
    monkeypatch.setattr(compile_api, "CompileEngine", lambda queue=None: engine)
    return TestClient(app), vault, queue, mock_llm


def write_source(vault: Path, source_id: str, title: str, content: str = "Raft 与 Paxos 的笔记。") -> None:
    store = WikiStore(vault, initialized=True)
    store.write_markdown(
        f"raw/{title}-{source_id}.md",
        {"id": source_id, "title": title, "kind": "note", "status": "normal"},
        content,
    )


def wait_for_status(client: TestClient, statuses: set[str], timeout: float = 10.0) -> dict[str, Any]:
    """轮询围观快照直到进入目标状态。"""

    deadline = time.time() + timeout
    snapshot: dict[str, Any] = {}
    while time.time() < deadline:
        snapshot = client.get("/api/compile/current").json()
        if snapshot.get("status") in statuses:
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"任务未在时限内进入 {statuses}，最后快照：{snapshot}")


def test_compile_idle_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _vault, _queue, _llm = install_env(tmp_path, monkeypatch, outputs=[valid_output()])

    response = client.get("/api/compile/current")
    assert response.status_code == 200
    assert response.json() == {"job_id": None, "status": "idle"}

    # 还没有任务时变更清单是 404。
    assert client.get("/api/changes").status_code == 404


def test_compile_all_pending_produces_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, vault, queue, mock_llm = install_env(tmp_path, monkeypatch, outputs=[valid_output()])
    write_source(vault, "aaaaaaaaaaaa", "共识笔记")

    with client:
        # 同一 client 上下文共享事件循环，后台编译任务才能持续推进。
        started = client.post("/api/compile", json={})
        assert started.status_code == 200
        payload = started.json()
        assert payload["queued_sources"] == 1
        job_id = payload["job_id"]

        snapshot = wait_for_status(client, {"done"})
        assert snapshot["job_id"] == job_id
        assert snapshot["kind"] == "compile"
        assert snapshot["done_sources"] == 1
        assert snapshot["total_sources"] == 1
        assert snapshot["can_leave"] is True
        assert snapshot["started_at"] is not None
        assert snapshot["finished_at"] is not None
        assert [step["name"] for step in snapshot["steps"]] == [
            "读取素材原文",
            "生成摘要页",
            "更新概念页与实体页",
            "重建索引与互链",
        ]
        assert all(step["state"] == "done" for step in snapshot["steps"])
        assert snapshot["cost"]["currency"] == "USD"

        # API-026 任务详情。
        detail = client.get(f"/api/compile/jobs/{job_id}").json()
        assert detail["status"] == "done"

        # API-027 变更清单：新建两页，含分区与 has_diff。
        changes = client.get("/api/changes").json()
        assert changes["job_id"] == job_id
        assert changes["status"] == "done"
        assert {(item["name"], item["change_type"]) for item in changes["items"]} == {
            ("共识算法摘要", "created"),
            ("Raft", "created"),
        }
        assert all(item["zone"] == "分布式系统" for item in changes["items"])
        assert changes["failed_sources"] == []

    # 编译后素材带 compiled_at，不再属于待编译集合。
    document = WikiStore(vault).read_markdown("raw/共识笔记-aaaaaaaaaaaa.md")
    assert document.metadata.get("compiled_at")

    with client:
        again = client.post("/api/compile", json={})
        assert again.status_code == 422
        assert "没有待编译" in again.json()["error"]["message"]

        # 显式指定 source_ids 也能触发（compiled_at 不拦截显式编译）。
        explicit = client.post("/api/compile", json={"source_ids": ["aaaaaaaaaaaa"]})
        assert explicit.status_code == 200
        wait_for_status(client, {"done"})
        assert len(mock_llm.requests) == 2


def test_zone_change_is_reported_with_zone_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, vault, _queue, _llm = install_env(
        tmp_path, monkeypatch, outputs=[valid_output(), zone_changed_output("知识管理")]
    )
    write_source(vault, "bbbbbbbbbbbb", "共识笔记")

    with client:
        assert client.post("/api/compile", json={}).status_code == 200
        wait_for_status(client, {"done"})
        first_changes = client.get("/api/changes").json()
        assert {item["change_type"] for item in first_changes["items"]} == {"created"}

        # 第二次编译同一素材：页面更新，且分区从 分布式系统 → 知识管理。
        assert client.post("/api/compile", json={"source_ids": ["bbbbbbbbbbbb"]}).status_code == 200
        wait_for_status(client, {"done"})

        changes = client.get("/api/changes").json()
        summary = next(item for item in changes["items"] if item["name"] == "共识算法摘要")
        assert summary["change_type"] == "zone_changed"
        assert summary["zone_before"] == "分布式系统"
        assert summary["zone"] == "知识管理"
        assert summary["has_diff"] is True
        # 摘要页与概念页分区一起变化，全部记为 zone_changed。
        assert {item["change_type"] for item in changes["items"]} == {"zone_changed"}


def test_partial_failure_keeps_pages_and_lists_failed_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, vault, _queue, _llm = install_env(
        tmp_path, monkeypatch, outputs=[valid_output(), "not-json"]
    )
    # 标题决定文件名排序：A 号先编译（成功），B 号后编译（失败）。
    write_source(vault, "cccccccccccc", "A好素材")
    write_source(vault, "dddddddddddd", "B坏素材", content="这份会解析失败。")

    with client:
        assert client.post("/api/compile", json={}).status_code == 200
        snapshot = wait_for_status(client, {"done"})

        assert snapshot["done_sources"] == 2  # 队列层面 done=total
        changes = client.get("/api/changes").json()
        assert len(changes["items"]) == 2  # 好素材的两个页面保留
        assert len(changes["failed_sources"]) == 1
        failed = changes["failed_sources"][0]
        assert failed["id"] == "dddddddddddd"
        assert "JSON" in failed["reason"]

        # 坏素材被标为 failed，且带失败原因。
        detail = client.get("/api/sources/dddddddddddd").json()
        assert detail["status"] == "failed"
        assert "JSON" in detail["failure_reason"]


def test_total_failure_marks_job_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, vault, _queue, _llm = install_env(tmp_path, monkeypatch, outputs=["not-json"])
    write_source(vault, "eeeeeeeeeeee", "坏素材")

    with client:
        assert client.post("/api/compile", json={}).status_code == 200
        snapshot = wait_for_status(client, {"failed"})
        assert "JSON" in (snapshot["failure_reason"] or "")
    assert WikiStore(vault).list_page_names() == []


def test_cost_budget_rejects_overspend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """预置成本流水后，超过上限的下一次调用必须被拒绝（TASK-015）。"""

    _client, vault, _queue, _llm = install_env(
        tmp_path, monkeypatch, outputs=[valid_output()], max_cost=0.5
    )
    costs_dir = vault / ".llmwiki"
    costs_dir.mkdir(parents=True, exist_ok=True)
    (costs_dir / "costs.json").write_text(
        json.dumps([{"job_id": "job-costly", "cost": 0.6}]),
        encoding="utf-8",
    )

    engine = CompileEngine(
        llm=MockLlm([valid_output()]),
        audit_service=MockAudit(),
        queue=JobQueue(config_store_override=config_store),
        config_store_override=config_store,
    )
    store = WikiStore(vault)

    with pytest.raises(AppError) as exc_info:
        asyncio.run(engine._ensure_cost_budget(Job(id="job-costly"), store))
    assert exc_info.value.code is ErrorCode.VALIDATION
    assert "上限" in exc_info.value.message

    # 上限内不拦截。
    asyncio.run(engine._ensure_cost_budget(Job(id="job-cheap"), store))
