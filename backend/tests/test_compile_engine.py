"""TASK-013：编译引擎核心编排验收测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from atlaswiki.compile import CompileEngine
from atlaswiki.compile.engine import _CompileManifest
from atlaswiki.config import ConfigStore, LlmSettings, Settings
from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.jobs import Job, JobQueue
from atlaswiki.schema import INGEST_PROMPT
from atlaswiki.workspace.store import PageDraft
from atlaswiki.workspace.store import WikiStore as MarkdownStore


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
    from atlaswiki.schema import PageType

    manifest = _CompileManifest(job_id="job-1")
    from atlaswiki.compile.engine import CompileChange

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


# ---------------------------------------------------------------------------
# TASK-014 / TASK-015 扩展验收
# ---------------------------------------------------------------------------


async def test_contradictions_land_in_frontmatter_for_lint(tmp_path: Path) -> None:
    """模型报出的矛盾要进摘要页 frontmatter，供体检扫描器消费。"""
    output = json.dumps(
        {
            "summary_page": {"title": "共识摘要", "zone": "分布式", "content": "存在分歧。"},
            "concept_pages": [],
            "entity_pages": [],
            "contradictions": [{"page": "Raft", "reason": "与既有页面的超时结论冲突"}],
        },
        ensure_ascii=False,
    )
    vault = tmp_path / "vault"
    write_source(vault)
    job, _queue, _llm, _audit, _events = await run_engine(tmp_path, vault, output)

    assert job.status.value == "done"
    store = MarkdownStore(vault)
    summary = store.read_page("共识摘要")
    assert summary.metadata["contradictions"] == [
        {"page": "Raft", "reason": "与既有页面的超时结论冲突"}
    ]
    assert "## 矛盾记录" in summary.content


def _segmented_output(segment_digest: str) -> str:
    return json.dumps(
        {
            "summary_page": {
                "title": "长文摘要",
                "zone": "长文",
                "content": f"综合结果：{segment_digest}",
            },
            "concept_pages": [],
            "entity_pages": [],
        },
        ensure_ascii=False,
    )


class RecordingSegmentLlm:
    """对分段摘要请求与最终合成请求返回不同输出。"""

    def __init__(self, final_output: str) -> None:
        self.final_output = final_output
        self.segment_requests: list[str] = []
        self.final_requests: list[str] = []

    async def complete(self, messages: list[dict[str, str]], *, json_mode: bool) -> str:
        system_prompt = messages[0]["content"]
        if "分段摘要器" in system_prompt:
            self.segment_requests.append(messages[1]["content"])
            return json.dumps(
                {"summary": "片段要点", "concepts": ["概念甲"], "entities": []},
                ensure_ascii=False,
            )
        self.final_requests.append(messages[1]["content"])
        return self.final_output


async def test_long_source_is_segmented_then_synthesized(tmp_path: Path) -> None:
    """超过阈值的长文走「分段摘要 → 合成」两阶段，短文保持单次调用。"""
    vault = tmp_path / "vault"
    config = make_config(tmp_path, vault, api_key="mock-key")
    # 把阈值压到很小，迫使一篇 600 字素材拆成多段。
    settings = config.load()
    settings.llm.segment_threshold_chars = 100
    config.save(settings)

    store = MarkdownStore(vault, initialized=True)
    long_content = "\n\n".join(f"第{index}段讨论共识协议的细节与权衡。" * 2 for index in range(20))
    assert len(long_content) > 100
    store.write_markdown(
        "raw/长文-111111111111.md",
        {"id": "111111111111", "title": "长文", "kind": "note", "status": "normal"},
        long_content,
    )

    queue = RecordingJobQueue(config_store_override=config)
    llm = RecordingSegmentLlm(_segmented_output("全部要点"))
    audit = MockAudit()
    engine = CompileEngine(llm=llm, audit_service=audit, queue=queue, config_store_override=config)
    job = await engine.start_compile(vault, ["111111111111"])
    await queue.join()

    assert job.status.value == "done"
    # 分段请求 ≥ 2 段，最终合成请求恰好 1 次。
    assert len(llm.segment_requests) >= 2
    assert len(llm.final_requests) == 1
    # 合成请求包含各段摘要与候选概念。
    assert "片段要点" in llm.final_requests[0]
    assert "概念甲" in llm.final_requests[0]
    assert MarkdownStore(vault).read_page("长文摘要")


async def test_same_source_recompile_reports_zone_change(tmp_path: Path) -> None:
    """同源重编译且分区变化时，变更清单记 zone_changed 并保留旧分区。"""
    vault = tmp_path / "vault"

    def output_with_zone(zone: str) -> str:
        payload = json.loads(valid_output())
        payload["summary_page"]["zone"] = zone
        return json.dumps(payload, ensure_ascii=False)

    write_source(vault)
    config = make_config(tmp_path, vault, api_key="mock-key")
    queue = RecordingJobQueue(config_store_override=config)

    engine = CompileEngine(
        llm=MockLlm(output_with_zone("分布式系统")),
        audit_service=MockAudit(),
        queue=queue,
        config_store_override=config,
    )
    job = await engine.start_compile(vault, ["src-1"])
    await queue.join()
    assert job.status.value == "done"

    # 把素材标回待编译，再用不同分区重编译。
    store = MarkdownStore(vault)
    document = store.read_markdown("raw/分布式系统笔记-src-1.md")
    store.write_markdown(
        "raw/分布式系统笔记-src-1.md",
        {**document.metadata, "status": "stale"},
        document.content,
    )
    engine2 = CompileEngine(
        llm=MockLlm(output_with_zone("新分区")),
        audit_service=MockAudit(),
        queue=queue,
        config_store_override=config,
    )
    job2 = await engine2.start_compile(vault, ["src-1"])
    await queue.join()
    assert job2.status.value == "done"

    manifest_path = vault / ".llmwiki" / "compile" / f"{job2.id}.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    summary_change = next(item for item in manifest["items"] if item["name"] == "共识算法摘要")
    assert summary_change["action"] == "zone_changed"
    assert summary_change["zone_before"] == "分布式系统"
    assert summary_change["zone"] == "新分区"
