"""TASK-021 / TASK-022 页面、搜索、图谱与分区 API 测试。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atlaswiki.api import pages
from atlaswiki.config import ConfigStore, Settings
from atlaswiki.main import app
from atlaswiki.schema import PageType
from atlaswiki.workspace.store import PageDraft, WikiStore


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """创建五页样本库：Alpha—Beta—Gamma、Delta—Alpha、Epsilon 为孤儿页。"""

    vault_path = tmp_path / "vault"
    store = WikiStore(vault_path, initialized=True)
    write_sample_page(
        store,
        "页面 Alpha",
        page_type="concept",
        zone="知识管理",
        title="Alpha 页面",
        content="包含 [[Beta]]。",
    )
    write_sample_page(
        store,
        "Beta",
        page_type="concept",
        zone="知识管理",
        title="Beta 概念",
        content="下一跳是 [[Gamma]]，回看 [[页面 Alpha]]。",
    )
    write_sample_page(
        store,
        "Gamma",
        page_type="source",
        zone="知识管理",
        title="Gamma 来源",
        content="量子编译材料中包含特殊关键词。",
    )
    write_sample_page(
        store,
        "Delta",
        page_type="analysis",
        zone="项目",
        title="Delta 分析",
        content="引用 [[页面 Alpha]]。",
    )
    write_sample_page(
        store,
        "Epsilon",
        page_type="entity",
        zone="知识管理",
        title="Epsilon 实体",
        content="没有链接的孤儿页。",
    )
    return store.initialize()


def write_sample_page(
    store: WikiStore,
    name: str,
    *,
    page_type: str,
    zone: str,
    title: str,
    content: str,
    human_edited: bool = False,
) -> None:
    """写入带完整 frontmatter 的测试页面。"""

    store.write_page(
        PageDraft(
            name=name,
            title=title,
            page_type=page_type,
            source_type="compiled",
            zone=zone,
            content=content,
            human_edited=human_edited,
        )
    )


@pytest.fixture
def client(vault: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """把全局配置替换为测试 vault，避免读取开发者机器上的设置。"""

    config = ConfigStore(tmp_path / "config")
    config.save(Settings(vault_path=str(vault)))
    monkeypatch.setattr(pages, "config_store", config)
    return TestClient(app)


def _configure_vault(tmp_path: Path, vault_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """在单个测试中切换到另一个样本 vault。"""

    config = ConfigStore(tmp_path / "config-large")
    config.save(Settings(vault_path=str(vault_path)))
    monkeypatch.setattr(pages, "config_store", config)


def test_page_list_filters_and_paginates(client: TestClient) -> None:
    """API-004：分页、分区筛选与类型筛选。"""

    response = client.get("/api/pages", params={"page": 1, "size": 2})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 5
    assert len(payload["items"]) == 2
    assert {"name", "title", "type", "zone", "link_count", "backlink_count"} <= payload["items"][
        0
    ].keys()

    concepts = client.get("/api/pages", params={"type": PageType.CONCEPT.value}).json()
    assert concepts["total"] == 2
    assert {item["name"] for item in concepts["items"]} == {"页面 Alpha", "Beta"}

    knowledge = client.get("/api/pages", params={"zone": "知识管理", "size": 2}).json()
    assert knowledge["total"] == 4
    assert len(knowledge["items"]) == 2

    page_two = client.get("/api/pages", params={"zone": "知识管理", "page": 2, "size": 2}).json()
    assert len(page_two["items"]) == 2

    invalid_type = client.get("/api/pages", params={"type": "unknown"})
    assert invalid_type.status_code == 422
    assert invalid_type.json()["error"]["code"] == "E_VALIDATION"


def test_page_detail_links_backlinks_and_sources(client: TestClient) -> None:
    """API-005：详情包含正文、出链、反链与来源区。"""

    response = client.get("/api/pages/%E9%A1%B5%E9%9D%A2%20Alpha")
    assert response.status_code == 200
    detail = response.json()
    assert detail["name"] == "页面 Alpha"
    assert detail["title"] == "Alpha 页面"
    assert detail["links"] == ["Beta"]
    assert detail["backlinks"] == [
        {"name": "Beta", "title": "Beta 概念"},
        {"name": "Delta", "title": "Delta 分析"},
    ]
    assert detail["sources"] == []

    missing = client.get("/api/pages/not-exists")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "E_NOT_FOUND"


def test_update_page_sets_human_edited(client: TestClient, vault: Path) -> None:
    """API-006：人工编辑正文并强制写 human_edited。"""

    response = client.put(
        "/api/pages/Beta",
        json={"content": "人工修订后的正文，链接 [[Gamma]]。"},
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["human_edited"] is True
    assert detail["content"].startswith("人工修订")
    assert detail["links"] == ["Gamma"]
    assert WikiStore(vault).read_page("Beta").metadata["human_edited"] is True

    empty = client.put("/api/pages/Beta", json={"content": ""})
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "E_VALIDATION"


def test_update_zone_changes_frontmatter(client: TestClient, vault: Path) -> None:
    """API-007：修改分区并保留 human_edited 标记。"""

    response = client.patch("/api/pages/Beta/zone", json={"zone": "新分区"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Beta"
    assert payload["zone_before"] == "知识管理"
    assert payload["zone"] == "新分区"
    assert payload["changed_at"]

    page = WikiStore(vault).read_page("Beta")
    assert page.metadata["zone"] == "新分区"
    assert page.metadata["human_edited"] is False


def test_backlinks_are_bidirectional_with_outlinks(client: TestClient) -> None:
    """API-008：同一批页面反链与出链双向一致。"""

    names = {item["name"] for item in client.get("/api/pages").json()["items"]}
    assert names == {"页面 Alpha", "Beta", "Gamma", "Delta", "Epsilon"}

    details = {name: client.get(f"/api/pages/{name}").json() for name in names}
    for source_name, detail in details.items():
        for target_name in detail["links"]:
            assert source_name in {
                item["name"] for item in details[target_name].get("backlinks", [])
            }

    assert {item["name"] for item in client.get("/api/pages/Gamma/backlinks").json()["items"]} == {
        "Beta"
    }


def test_page_diff_returns_working_tree_unified_diff(client: TestClient, vault: Path) -> None:
    """API-009：相对 git HEAD 返回页面差异。"""

    subprocess.run(["git", "init"], cwd=vault, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test"], cwd=vault, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@local"], cwd=vault, check=True, capture_output=True
    )
    subprocess.run(["git", "add", "."], cwd=vault, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=vault, check=True, capture_output=True)

    assert client.put("/api/pages/Gamma", json={"content": "新的量子正文。"}).status_code == 200
    response = client.get("/api/pages/Gamma/diff")
    assert response.status_code == 200
    diff = response.json()["diff"]
    assert "wiki/sources/Gamma.md" in diff
    assert "+新的量子正文。" in diff


def test_graph_depth_orphans_and_zone_edges(client: TestClient) -> None:
    """API-010：一跳/二跳邻域、孤点与分区过滤。"""

    full = client.get("/api/graph").json()
    assert full["node_count"] == 5
    assert {node["id"] for node in full["nodes"]} == {
        "页面 Alpha",
        "Beta",
        "Gamma",
        "Delta",
        "Epsilon",
    }
    assert next(node for node in full["nodes"] if node["id"] == "Epsilon")["degree"] == 0
    # Wiki 图谱边保留方向：Alpha↔Beta 是两条边，Beta→Gamma 与 Delta→Alpha 各一条。
    assert len(full["edges"]) == 4

    depth_one = client.get("/api/graph", params={"center": "页面 Alpha", "depth": 1}).json()
    assert {node["id"] for node in depth_one["nodes"]} == {"页面 Alpha", "Beta", "Delta"}
    assert depth_one["edge_count"] == 3

    depth_two = client.get("/api/graph", params={"center": "页面 Alpha", "depth": 2}).json()
    assert {node["id"] for node in depth_two["nodes"]} == {"页面 Alpha", "Beta", "Delta", "Gamma"}
    assert depth_two["edge_count"] == 4

    zone_graph = client.get("/api/graph", params={"zone": "知识管理"}).json()
    node_names = {node["id"] for node in zone_graph["nodes"]}
    assert node_names == {"页面 Alpha", "Beta", "Gamma", "Epsilon"}
    assert all(
        edge["source"] in node_names and edge["target"] in node_names
        for edge in zone_graph["edges"]
    )
    assert zone_graph["truncated"] is False


def test_graph_truncates_depth_two_over_300_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API-010：depth=2 超过 300 个节点时进行规模保护。"""

    vault_path = tmp_path / "vault-large"
    store = WikiStore(vault_path, initialized=True)
    write_sample_page(
        store, "Center", page_type="concept", zone="all", title="Center", content="Hub"
    )
    for number in range(1, 302):
        write_sample_page(
            store,
            f"Page {number:03d}",
            page_type="concept",
            zone="all",
            title=f"Page {number:03d}",
            content="[[Center]]",
        )
    store.initialize()

    config = ConfigStore(tmp_path / "config-large")
    config.save(Settings(vault_path=str(vault_path)))
    monkeypatch.setattr(pages, "config_store", config)

    response = TestClient(app)
    payload = response.get(
        "/api/graph",
        params={"center": "Center", "depth": 2},
    ).json()
    assert payload["node_count"] == 300
    assert payload["truncated"] is True
    assert all(
        edge["source"] in {node["id"] for node in payload["nodes"]} for edge in payload["edges"]
    )


def test_zone_list_and_zone_pages(client: TestClient) -> None:
    """API-011 / API-012：分区总数守恒，分区内页面正确。"""

    zones = client.get("/api/zones").json()
    assert zones == [
        {"name": "知识管理", "page_count": 4},
        {"name": "项目", "page_count": 1},
    ]
    assert sum(zone["page_count"] for zone in zones) == 5

    response = client.get("/api/zones/%E7%9F%A5%E8%AF%86%E7%AE%A1%E7%90%86/pages")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert {item["name"] for item in payload["items"]} == {
        "页面 Alpha",
        "Beta",
        "Gamma",
        "Epsilon",
    }


def test_search_marks_query_and_validates_length(client: TestClient) -> None:
    """API-013：标题/正文命中、<mark> 位置和查询校验。"""

    response = client.get("/api/search", params={"q": "量子", "size": 1})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["query"] == "量子"
    item = payload["items"][0]
    assert item["name"] == "Gamma"
    assert "<mark>量子</mark>" in item["snippet"]
    assert item["snippet"].index("<mark>量子</mark>") <= 40 + len("<mark>")

    title_hit = client.get("/api/search", params={"q": "Alpha"}).json()
    assert title_hit["total"] >= 2
    assert all("<mark>Alpha</mark>" in item["snippet"] for item in title_hit["items"])

    empty = client.get("/api/search", params={"q": " "})
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "E_VALIDATION"

    long = client.get("/api/search", params={"q": "a" * 101})
    assert long.status_code == 422
    assert long.json()["error"]["code"] == "E_VALIDATION"
