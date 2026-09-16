"""TASK-029 / TASK-030：体检扫描、报告、忽略与结构性修复验收测试。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from atlaswiki.config import Settings, config_store
from atlaswiki.jobs import Job, JobQueue, job_queue
from atlaswiki.lint import LintScanner, LintService
from atlaswiki.lint.store import read_report, report_path
from atlaswiki.workspace.store import PageDraft, WikiStore


class FakeConfigStore:
    """测试专用配置仓库，避免污染本机设置。"""

    def __init__(self, vault_path: Path) -> None:
        self._settings = Settings(vault_path=str(vault_path))

    def load(self) -> Settings:
        return self._settings


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    return tmp_path / "vault"


@pytest.fixture
def queue(vault: Path) -> JobQueue:
    return JobQueue(FakeConfigStore(vault))


@pytest.fixture
def service(vault: Path, queue: JobQueue) -> LintService:
    return LintService(queue=queue, config_store_override=FakeConfigStore(vault))


def write_page(
    store: WikiStore,
    name: str,
    *,
    page_type: str,
    zone: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """写一个可通过存储层校验的 wiki 页面。"""

    store.write_page(
        PageDraft(
            name=name,
            title=name,
            page_type=page_type,
            source_type="compiled",
            zone=zone,
            content=content,
            metadata=metadata or {},
        )
    )


def build_sample(vault: Path) -> WikiStore:
    """构造同时命中矛盾、孤儿、失效链接、缺索引和分区混杂的样本。"""

    store = WikiStore(vault, initialized=True)
    write_page(
        store,
        "矛盾页",
        page_type="concept",
        zone="正常区",
        content="结论见 [[互链页]]。",
        metadata={"contradictions": ["两个来源对启动时间描述冲突"]},
    )
    write_page(store, "孤儿页", page_type="concept", zone="正常区", content="孤立的正文。")
    write_page(store, "失效页", page_type="concept", zone="正常区", content="参见 [[不存在页]]。")
    write_page(store, "互链页", page_type="concept", zone="正常区", content="关联 [[矛盾页]]。")
    write_page(store, "素材记录", page_type="source", zone="混合区", content="来源见 [[矛盾页]]。")
    write_page(store, "实体记录", page_type="entity", zone="混合区", content="实体见 [[矛盾页]]。")
    write_page(store, "分析记录", page_type="analysis", zone="混合区", content="分析见 [[矛盾页]]。")
    return store


def standalone_job() -> Job:
    """构造不进入队列的扫描回调任务。"""

    return Job(kind="manual")


async def test_scan_finds_all_five_issue_kinds_and_is_read_only(vault: Path) -> None:
    build_sample(vault)
    before = {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*.md")
    }

    issues = await LintScanner().scan(vault)
    kinds = {issue["kind"] for issue in issues}

    assert kinds == {"contradiction", "orphan", "dead_link", "missing_index", "zone_mix"}
    assert not (vault / ".llmwiki" / "lint-report.json").exists()
    assert next(issue for issue in issues if issue["kind"] == "dead_link")["repairable"] is True
    assert next(issue for issue in issues if issue["kind"] == "missing_index")["repairable"] is True
    for kind in ("contradiction", "orphan", "zone_mix"):
        assert next(issue for issue in issues if issue["kind"] == kind)["repairable"] is False
    after = {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in vault.rglob("*.md")
    }
    assert after == before


async def test_report_contains_graph_metrics_and_preserves_ignore(vault: Path, service: LintService) -> None:
    build_sample(vault)
    await service.scan_and_save(standalone_job(), vault)
    report = read_report(vault)
    assert report is not None
    assert report["metrics"]["orphan_ratio"] == pytest.approx(1 / 7)
    assert report["metrics"]["average_out_links"] > 0

    dead = next(issue for issue in report["issues"] if issue["kind"] == "dead_link")
    await service.ignore_issue(dead["id"], "等待新建目标页面")
    ignored_report = read_report(vault)
    assert ignored_report is not None
    assert next(issue for issue in ignored_report["issues"] if issue["id"] == dead["id"])["ignore_reason"] == "等待新建目标页面"

    await service.scan_and_save(standalone_job(), vault)
    latest = read_report(vault)
    assert latest is not None
    latest_dead = next(issue for issue in latest["issues"] if issue["id"] == dead["id"])
    assert latest_dead["ignored"] is True
    assert latest_dead["ignore_reason"] == "等待新建目标页面"


async def test_fix_removes_structural_dead_link_and_rebuilds_index(vault: Path, service: LintService) -> None:
    store = build_sample(vault)
    await service.scan_and_save(standalone_job(), vault)
    report = read_report(vault)
    assert report is not None

    dead = next(issue for issue in report["issues"] if issue["kind"] == "dead_link")
    missing = next(issue for issue in report["issues"] if issue["kind"] == "missing_index")

    dead_job = await service.fix_issue(dead["id"])
    index_job = await service.fix_issue(missing["id"])
    await service.queue.join()
    assert dead_job.status.value == "done"
    assert index_job.status.value == "done"

    page = store.read_page("失效页")
    assert "[[不存在页]]" not in page.content
    assert "不存在页" in page.content
    assert (vault / "wiki" / "index.md").is_file()
    fresh_issues = await LintScanner().scan(vault)
    assert all(item["kind"] != "dead_link" for item in fresh_issues)
    assert all(item["kind"] != "missing_index" for item in fresh_issues)


async def test_fix_annotates_dead_link_without_overwriting_human_page(vault: Path, service: LintService) -> None:
    store = WikiStore(vault, initialized=True)
    store.write_markdown(
        "wiki/concepts/人工页.md",
        {
            "title": "人工页",
            "type": "concept",
            "source_type": "human",
            "zone": "人工区",
            "human_edited": True,
            "status": "active",
            "links": ["不存在页"],
        },
        "这是人工保留的 [[不存在页]] 记录。",
    )
    await service.scan_and_save(standalone_job(), vault)
    report = read_report(vault)
    assert report is not None
    dead = next(issue for issue in report["issues"] if issue["kind"] == "dead_link")

    await service.fix_issue(dead["id"])
    await service.queue.join()

    page = store.read_page("人工页")
    assert page.content == "这是人工保留的 [[不存在页]] 记录。"
    fixed_report = read_report(vault)
    assert fixed_report is not None
    current = next(issue for issue in fixed_report["issues"] if issue["id"] == dead["id"])
    assert current["manual_required"] is True
    assert "人工确认" in current["suggestion"]


async def test_idle_check_respects_report_age_and_can_force(vault: Path, service: LintService) -> None:
    build_sample(vault)
    assert await service.idle_check() is not None
    await service.queue.join()

    # 刚生成的报告不应重复触发。
    assert await service.idle_check(idle_minutes=30) is None
    forced = await service.idle_check(force=True)
    assert forced is not None
    await service.queue.join()


@pytest.fixture
async def api_client(vault: Path) -> AsyncIterator[httpx.AsyncClient]:
    """为 API 测试替换全局配置缓存。"""

    config_store._cache = Settings(vault_path=str(vault))
    transport = httpx.ASGITransport(app=_app())
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    yield client
    await client.aclose()


def _app() -> Any:
    from atlaswiki.main import app

    return app


async def test_lint_api_run_report_ignore_and_validation(
    vault: Path,
    api_client: httpx.AsyncClient,
    service: LintService,
) -> None:
    build_sample(vault)

    run_response = await api_client.post("/api/lint/run")
    assert run_response.status_code == 200
    job_id = run_response.json()["job_id"]
    assert job_queue.get(job_id) is not None
    await job_queue.join()

    # API 提交使用全局 queue；全局任务完成后报告已落盘。
    report_response = await api_client.get("/api/lint/report")
    assert report_response.status_code == 200
    report = report_response.json()
    assert len(report["issues"]) > 0
    assert set(report["metrics"]) >= {"orphan_ratio", "average_out_links"}

    dead = next(issue for issue in report["issues"] if issue["kind"] == "dead_link")
    missing_reason = await api_client.post(f"/api/lint/issues/{dead['id']}/ignore")
    assert missing_reason.status_code == 422
    assert missing_reason.json()["error"]["code"] == "E_VALIDATION"

    ignored = await api_client.post(
        f"/api/lint/issues/{dead['id']}/ignore",
        json={"reason": "目标页面稍后创建"},
    )
    assert ignored.status_code == 200
    assert ignored.json() == {"ok": True, "issue": ignored.json()["issue"]}
    assert read_report(vault) is not None

    persisted = json.loads(report_path(vault).read_text("utf-8"))
    assert next(item for item in persisted["issues"] if item["id"] == dead["id"])["ignored"] is True


async def test_lint_api_fix_rejects_semantic_issue(vault: Path, api_client: httpx.AsyncClient, service: LintService) -> None:
    build_sample(vault)
    await service.scan_and_save(standalone_job(), vault)
    report = read_report(vault)
    assert report is not None
    orphan = next(issue for issue in report["issues"] if issue["kind"] == "orphan")

    response = await api_client.post(f"/api/lint/issues/{orphan['id']}/fix")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E_VALIDATION"
