"""TASK-013：编译引擎核心编排验收测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from llmwiki.compile import CompileEngine
from llmwiki.compile.engine import _CompileManifest
from llmwiki.config import ConfigStore, LlmSettings, Settings
from llmwiki.errors import AppError, ErrorCode
from llmwiki.jobs import Job, JobQueue
from llmwiki.schema import INGEST_PROMPT
from llmwiki.workspace.store import PageDraft
from llmwiki.workspace.store import WikiStore as MarkdownStore


@dataclass
class MockLlm:
    """捕获请求并返回固定 JSON 的 mock 客户端。"""

    output: str
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def complete(self, messages: list[dict[str, str]], *, json_mode: bool) -> str:
        self.requests.append({"messages": messages, "json_mode": json_mode})
        return self.output


@dataclass
class MockAudit:
    """避免测试依赖本机 git 身份与远端。"""

    calls: list[dict[str, Any]] = field(default_factory=list)

    def record_task_completion(self, **payload: Any) -> dict[str, Any]:
        self.calls.append(payload)
        return {"ok": True}


def make_config(tmp_path: Path, vault: Path, *, api_key: str = "") -> ConfigStore:
    """返回隔离配置仓库。"""
    store = ConfigStore(tmp_path / "config")
    store.save(
        Settings(
            vault_path=str(vault),
            llm=LlmSettings(api_key=api_key, base_url="https://llm.example/v1"),
        )
    )
    return store


def write_source(vault: Path, source_id: str = "src-1", title: str = "分布式系统笔记") -> None:
    """写入一份 raw/ 手写素材。"""
    store = MarkdownStore(vault, initialized=True)
    store.write_markdown(
        f"raw/{title}-{source_id}.md",
        {
            "id": source_id,
            "title": title,
            "kind": "note",
            "status": "normal",
        },
        "Raft 需要多数派确认，Paxos 是另一个共识算法。",
    )


def valid_output() -> str:
    """构造符合 INGEST_PROMPT 的模型输出。"""
    return json.dumps(
        {
            "summary_page": {
                "title": "共识算法摘要",
                "zone": "分布式系统",
                "content": "本素材讨论共识算法，重点见 [[Raft]] 与 [[Paxos]]。",
            },
            "concept_pages": [
                {
                    "title": "Raft",
                    "zone": "分布式系统",
                    "content": "Raft 是易实现的共识算法。",
                    "links": ["共识算法摘要", "Paxos"],
                }
            ],
            "entity_pages": [
                {
                    "title": "Paxos",
                    "zone": "分布式系统",
                    "content": "Paxos 是早期共识协议。",
                    "links": ["共识算法摘要", "Raft"],
                }
            ],
            "contradictions": [],
        },
        ensure_ascii=False,
    )


class RecordingJobQueue(JobQueue):
    """捕获引擎通过 publish() 发出的步骤事件。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.published: list[dict[str, Any]] = []

    async def publish(self, event: str, **payload: Any) -> None:
        await super().publish(event, **payload)
        self.published.append({"event": event, **payload})


async def run_engine(
    tmp_path: Path,
    vault: Path,
    output: str,
    *,
    source_ids: list[str] | None = None,
) -> tuple[Job, JobQueue, MockLlm, MockAudit, list[dict[str, Any]]]:
    """执行一个完整编译任务并收集事件。"""
    config = make_config(tmp_path, vault, api_key="mock-key")
    queue = RecordingJobQueue(config_store_override=config)
    llm = MockLlm(output)
    audit = MockAudit()
    engine = CompileEngine(llm=llm, audit_service=audit, queue=queue, config_store_override=config)
    job = await engine.start_compile(vault, source_ids or ["src-1"])
    await queue.join()
    return job, queue, llm, audit, queue.published


async def test_normal_compile_writes_linked_pages_frontmatter_and_index(
    tmp_path: Path,
) -> None:
    """正常编译应写入摘要/概念/实体页、互链、frontmatter 和索引。"""
    vault = tmp_path / "vault"
    write_source(vault)
    job, _queue, llm, audit, events = await run_engine(tmp_path, vault, valid_output())

    store = MarkdownStore(vault)
    assert job.status.value == "done"
    assert job.progress == 1.0
    assert len(llm.requests) == 1
    assert llm.requests[0]["json_mode"] is True
    assert llm.requests[0]["messages"][0]["content"] == INGEST_PROMPT
    assert "分布式系统笔记" in llm.requests[0]["messages"][1]["content"]

    summary = store.read_page("共识算法摘要")
    concept = store.read_page("Raft")
    entity = store.read_page("Paxos")
    assert summary.metadata["type"] == "source"
    assert summary.metadata["origin_source"] == "src-1"
    assert summary.metadata["zone"] == "分布式系统"
    assert summary.metadata["links"] == ["Raft", "Paxos"]
    assert concept.metadata["links"] == ["共识算法摘要", "Paxos"]
    assert entity.metadata["links"] == ["共识算法摘要", "Raft"]
    assert store.out_links("共识算法摘要") == ["Raft", "Paxos"]
    assert store.back_links("Raft") == ["Paxos", "共识算法摘要"]

    index = (vault / "wiki" / "index.md").read_text("utf-8")
    for name in ("共识算法摘要", "Raft", "Paxos"):
        assert name in index
    assert any(event.get("step") == "调用 LLM 生成结构化结果" for event in events)
    assert audit.calls[0]["operation_type"] == "compile"


async def test_missing_api_key_raises_not_configured(tmp_path: Path) -> None:
    """默认 LLM 契约在无 key 时必须返回 E_LLM_NOT_CONFIGURED。"""
    vault = tmp_path / "vault"
    write_source(vault)
    config = make_config(tmp_path, vault, api_key="")
    engine = CompileEngine(queue=JobQueue(config_store_override=config), config_store_override=config)

    with pytest.raises(AppError) as exc_info:
        await engine.compile_sources(Job(), vault, ["src-1"])

    assert exc_info.value.code is ErrorCode.LLM_NOT_CONFIGURED
    assert MarkdownStore(vault).list_page_names() == []


async def test_page_conflict_is_renamed_and_existing_page_is_preserved(tmp_path: Path) -> None:
    """不同来源的同名页面必须改名，不能覆盖旧页面。"""
    vault = tmp_path / "vault"
    write_source(vault)
    store = MarkdownStore(vault, initialized=True)
    store.write_page(
        PageDraft(
            name="Raft",
            title="旧 Raft",
            page_type="concept",
            source_type="compiled",
            zone="旧分区",
            content="旧内容",
            origin_source="old-source",
        )
    )

    _job, _queue, _llm, _audit, _events = await run_engine(tmp_path, vault, valid_output())
    renamed = store.read_page("Raft-2")
    old = store.read_page("Raft")

    assert renamed.metadata["title"] == "Raft"
    assert renamed.metadata["origin_source"] == "src-1"
    assert old.metadata["title"] == "旧 Raft"
    assert old.content == "旧内容"
    assert old.metadata["origin_source"] == "old-source"


async def test_invalid_llm_json_writes_no_wiki_page(tmp_path: Path) -> None:
    """结构化结果非法时必须先失败，不能写坏文件。"""
    vault = tmp_path / "vault"
    write_source(vault)
    config = make_config(tmp_path, vault, api_key="mock-key")
    queue = JobQueue(config_store_override=config)
    engine = CompileEngine(
        llm=MockLlm("not-json"),
        audit_service=MockAudit(),
        queue=queue,
        config_store_override=config,
    )
    job = await engine.start_compile(vault, ["src-1"])
    await queue.join()

    assert job.status.value == "failed"
    assert "LLM 输出不是有效 JSON" in (job.error or "")
    assert MarkdownStore(vault).list_page_names() == []


def test_manifest_serializes_runtime_changes(tmp_path: Path) -> None:
    """变更清单载体应能序列化页面路径和动作。"""
    from llmwiki.schema import PageType

    manifest = _CompileManifest(job_id="job-1")
    from llmwiki.compile.engine import CompileChange

    manifest.items.append(
        CompileChange(
            name="页面",
            title="页面",
            page_type=PageType.CONCEPT,
            action="created",
            path=Path("wiki/concepts/页面.md"),
        )
    )
    data = manifest.to_dict()

    assert data["items"][0]["path"] == "wiki/concepts/页面.md"
    assert data["items"][0]["page_type"] == "concept"
