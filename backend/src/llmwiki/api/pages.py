"""页面、反链、搜索、图谱与分区读接口（API-004 ~ API-013）。"""

from __future__ import annotations

import re
import subprocess
from html import escape
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from llmwiki.config import config_store
from llmwiki.errors import AppError, ErrorCode
from llmwiki.schema import PageStatus, PageType, SourceType
from llmwiki.workspace.links import LinkIndex
from llmwiki.workspace.store import Page, WikiStore

router = APIRouter(prefix="/api", tags=["pages"])

_GRAPH_NODE_LIMIT = 300
_SNIPPET_CONTEXT = 40
_SEARCH_QUERY_LIMIT = 100


class PageUpdateRequest(BaseModel):
    """人工编辑保存请求；API-006 目前只开放正文。"""

    content: str = Field(min_length=1)

    @classmethod
    def parse(cls, body: dict[str, Any] | None) -> PageUpdateRequest:
        """显式校验，确保 FastAPI 返回统一 ErrorBody，而非默认 validation body。"""

        content = body.get("content") if isinstance(body, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise AppError(
                ErrorCode.VALIDATION,
                "正文不能为空",
                {"fields": [{"field": "content", "reason": "必填"}]},
            )
        return cls(content=content)


class ZoneUpdateRequest(BaseModel):
    """分区修改请求。"""

    zone: str = Field(min_length=1, max_length=80)


def _store() -> WikiStore:
    """从全局配置解析 vault；未配置或缺少骨架时返回业务错误。"""

    vault_path = config_store.load().vault_path
    if not vault_path:
        raise AppError(ErrorCode.VALIDATION, "尚未配置 vault 路径", {"fields": ["vault_path"]})
    store = WikiStore(Path(vault_path).expanduser().resolve())
    if not store.initialized:
        raise AppError(
            ErrorCode.NOT_FOUND, "vault 不存在或尚未初始化", {"vault_path": str(store.vault)}
        )
    return store


def _metadata_value(page: Page, key: str, default: str) -> str:
    """读取 frontmatter 字符串值，非法类型时回退默认值。"""

    value = page.metadata.get(key, default)
    return value if isinstance(value, str) else default


def _page_type(page: Page) -> PageType:
    """安全解析页面类型；样本库损坏时返回明确校验错误。"""

    try:
        return page.page_type
    except (KeyError, ValueError) as exc:
        raise AppError(
            ErrorCode.VALIDATION,
            "页面 type 无效",
            {"name": page.name, "type": page.metadata.get("type")},
        ) from exc


def _source_type(page: Page) -> SourceType:
    """安全解析来源类型，兼容人工创建但缺少字段的页面。"""

    value = page.metadata.get("source_type")
    try:
        return SourceType(value) if value is not None else SourceType.COMPILED
    except ValueError as exc:
        raise AppError(
            ErrorCode.VALIDATION,
            "页面 source_type 无效",
            {"name": page.name, "source_type": value},
        ) from exc


def _page_status(page: Page) -> PageStatus:
    """安全解析页面状态。"""

    value = page.metadata.get("status", PageStatus.ACTIVE.value)
    try:
        return PageStatus(value)
    except ValueError as exc:
        raise AppError(
            ErrorCode.VALIDATION,
            "页面 status 无效",
            {"name": page.name, "status": value},
        ) from exc


def _unique_links(page: Page) -> list[str]:
    """保持正文出现顺序的去重出链，包含失效链接。"""

    return list(dict.fromkeys(link.target for link in page.links if link.target))


def _page_summary(page: Page, index: LinkIndex) -> dict[str, Any]:
    """构造 PageSummary 响应。"""

    links = _unique_links(page)
    return {
        "name": page.name,
        "title": _metadata_value(page, "title", page.name),
        "type": _page_type(page).value,
        "zone": _metadata_value(page, "zone", ""),
        "source_type": _source_type(page).value,
        "human_edited": page.metadata.get("human_edited") is True,
        "status": _page_status(page).value,
        "link_count": len(links),
        "backlink_count": len(index.back_links.get(page.name, [])),
        "updated_at": _metadata_value(page, "updated_at", ""),
    }


def _page_detail(page: Page, index: LinkIndex, store: WikiStore) -> dict[str, Any]:
    """构造 PageDetail 响应。"""

    summary = _page_summary(page, index)
    backlinks = [
        {"name": source_name, "title": _metadata_value(source, "title", source.name)}
        for source_name in index.back_links.get(page.name, [])
        if (source := _safe_read_page(store, source_name)) is not None
    ]
    return {
        **summary,
        "created_at": _metadata_value(page, "created_at", ""),
        "origin_source": _metadata_value(page, "origin_source", "") or None,
        "content": page.content,
        "links": _unique_links(page),
        "backlinks": backlinks,
        "sources": _page_sources(store, page),
    }


def _safe_read_page(store: WikiStore, name: str) -> Page | None:
    """读取页面；链接目标不存在或样本损坏时不让详情接口整体失败。"""

    try:
        return store.read_page(name)
    except AppError:
        return None


def _page_sources(store: WikiStore, page: Page) -> list[dict[str, str]]:
    """由 origin_source 推导来源区数据。"""

    source_id = _metadata_value(page, "origin_source", "")
    if not source_id:
        return []

    raw_dir = store.vault / "raw"
    if not raw_dir.is_dir():
        return []
    for path in sorted(raw_dir.glob("*.md")):
        source = _safe_read_markdown(store, path.relative_to(store.vault))
        if source is None or source.metadata.get("id") != source_id:
            continue
        return [
            {
                "id": source_id,
                "title": str(source.metadata.get("title") or source_id),
                "kind": str(source.metadata.get("kind") or "note"),
            }
        ]
    return [{"id": source_id, "title": source_id, "kind": "unknown"}]


def _safe_read_markdown(store: WikiStore, relative_path: Path):
    """读取 raw Markdown；文件损坏时返回 None，避免列表接口被单个文件阻塞。"""

    try:
        return store.read_markdown(relative_path)
    except AppError:
        return None


def _validate_type(raw_type: str | None) -> PageType | None:
    """校验可选页面类型筛选。"""

    if raw_type is None:
        return None
    try:
        return PageType(raw_type)
    except ValueError as exc:
        raise AppError(
            ErrorCode.VALIDATION,
            "type 参数无效",
            {"fields": [{"field": "type", "reason": "必须是 source/concept/entity/analysis"}]},
        ) from exc


def _paginate(
    items: list[dict[str, Any]], page: int, size: int
) -> tuple[list[dict[str, Any]], int]:
    """列表接口统一分页；page/size 基本边界由 FastAPI Query 保证。"""

    start = (page - 1) * size
    return items[start : start + size], len(items)


def _filtered_pages(
    store: WikiStore,
    *,
    zone: str | None = None,
    page_type: PageType | None = None,
) -> tuple[list[Page], LinkIndex]:
    """读取并筛选页面；索引只构建一次。"""

    index = store.link_index()
    pages = store.read_pages()
    if zone is not None:
        pages = [page for page in pages if _metadata_value(page, "zone", "") == zone]
    if page_type is not None:
        pages = [page for page in pages if _page_type(page) is page_type]
    return pages, index


@router.get("/pages")
async def list_pages(
    zone: str | None = None,
    type: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """API-004：按分区与类型筛选页面。"""

    store = _store()
    pages, index = _filtered_pages(store, zone=zone, page_type=_validate_type(type))
    items, total = _paginate([_page_summary(item, index) for item in pages], page, size)
    return {"items": items, "total": total}


@router.get("/graph")
async def get_graph(
    zone: str | None = None,
    depth: int = Query(1, ge=1, le=2),
    center: str | None = None,
) -> dict[str, Any]:
    """API-010：返回全库或中心页面邻域图谱。"""

    store = _store()
    pages, index = _filtered_pages(store, zone=zone)
    pages_by_name = {page.name: page for page in pages}
    candidate_names = set(pages_by_name)
    truncated = False

    if center is not None:
        normalized_center = store.read_page(center).name
        if normalized_center not in candidate_names:
            return {
                "nodes": [],
                "edges": [],
                "truncated": False,
                "node_count": 0,
                "edge_count": 0,
            }

        adjacency: dict[str, set[str]] = {name: set() for name in candidate_names}
        for source, target in index.edges:
            if source in candidate_names and target in candidate_names:
                adjacency[source].add(target)
                adjacency[target].add(source)

        # BFS 按“中心 → 直接邻居 → 二跳邻居”发现节点。
        ordered_nodes = _bfs_order(adjacency, normalized_center, depth)
        selected_names = set(ordered_nodes)
        if len(selected_names) > _GRAPH_NODE_LIMIT:
            selected_names = set(ordered_nodes[:_GRAPH_NODE_LIMIT])
            truncated = True
    else:
        ordered_names = sorted(candidate_names)
        selected_names = set(ordered_names)
        if len(selected_names) > _GRAPH_NODE_LIMIT:
            selected_names = set(ordered_names[:_GRAPH_NODE_LIMIT])
            truncated = True

    edges = [
        {"source": source, "target": target}
        for source, target in index.edges
        if source in selected_names and target in selected_names
    ]
    nodes = [
        {
            "id": name,
            "title": _metadata_value(page := pages_by_name[name], "title", name),
            "type": _page_type(page).value,
            "zone": _metadata_value(page, "zone", ""),
            "degree": sum(edge["source"] == name or edge["target"] == name for edge in edges),
            "status": _page_status(page).value,
        }
        for name in sorted(selected_names)
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _bfs_order(adjacency: dict[str, set[str]], center: str, depth: int) -> list[str]:
    """按图距离返回中心邻域节点顺序，供规模保护截断。"""

    ordered = [center]
    visited = {center}
    current_layer = [center]
    for _layer in range(depth):
        next_layer: list[str] = []
        for current in current_layer:
            for neighbor in sorted(adjacency[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    ordered.append(neighbor)
                    next_layer.append(neighbor)
        current_layer = next_layer
    return ordered


@router.get("/zones")
async def list_zones() -> list[dict[str, Any]]:
    """API-011：返回分区及页面计数。"""

    store = _store()
    counts: dict[str, int] = {}
    for page in store.read_pages():
        zone = _metadata_value(page, "zone", "")
        counts[zone] = counts.get(zone, 0) + 1
    return [{"name": name, "page_count": count} for name, count in sorted(counts.items())]


@router.get("/zones/{name}/pages")
async def list_zone_pages(
    name: str,
    type: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """API-012：返回指定分区下的页面。"""

    return await list_pages(zone=name, type=type, page=page, size=size)


@router.get("/search")
async def search(
    q: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """API-013：标题与正文简单文本搜索，并生成后端高亮片段。"""

    query = q.strip() if q is not None else ""
    if not query:
        raise AppError(
            ErrorCode.VALIDATION,
            "搜索关键词不能为空",
            {"fields": [{"field": "q", "reason": "必填"}]},
        )
    if len(query) > _SEARCH_QUERY_LIMIT:
        raise AppError(
            ErrorCode.VALIDATION,
            "搜索关键词过长",
            {"fields": [{"field": "q", "reason": f"长度不能超过 {_SEARCH_QUERY_LIMIT}"}]},
        )

    store = _store()
    pages, _ = _filtered_pages(store)
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    results: list[dict[str, Any]] = []
    for wiki_page in pages:
        haystack = f"{_metadata_value(wiki_page, 'title', wiki_page.name)}\n{wiki_page.content}"
        match = pattern.search(haystack)
        if match is None:
            continue
        results.append(
            {
                "name": wiki_page.name,
                "title": _metadata_value(wiki_page, "title", wiki_page.name),
                "zone": _metadata_value(wiki_page, "zone", ""),
                "type": _page_type(wiki_page).value,
                "snippet": _highlight_snippet(haystack, pattern),
            }
        )

    items, total = _paginate(results, page, size)
    return {"items": items, "total": total, "query": query}


def _highlight_snippet(text: str, pattern: re.Pattern[str]) -> str:
    """取命中位置前后各约 40 字，并转义后插入 <mark>。"""

    match = pattern.search(text)
    if match is None:
        return escape(text[: _SNIPPET_CONTEXT * 2])

    start = max(0, match.start() - _SNIPPET_CONTEXT)
    end = min(len(text), match.end() + _SNIPPET_CONTEXT)
    snippet = text[start:end]
    return pattern.sub(lambda item: f"<mark>{escape(item.group(0))}</mark>", escape(snippet))


# 特殊路径必须先于 /pages/{name:path} 注册，避免被详情 catch-all 拦截。
@router.patch("/pages/{name}/zone")
async def update_page_zone(name: str, body: ZoneUpdateRequest) -> dict[str, Any]:
    """API-007：修改页面分区并返回变更前后值。"""

    store = _store()
    current = store.read_page(name)
    zone_before = _metadata_value(current, "zone", "")
    updated = store.write_page(
        _draft_from_page(
            current, zone=body.zone, human_edited=current.metadata.get("human_edited") is True
        ),
        overwrite=True,
    )
    return {
        "name": updated.name,
        "zone": _metadata_value(updated, "zone", ""),
        "zone_before": zone_before,
        "changed_at": _metadata_value(updated, "updated_at", ""),
    }


@router.get("/pages/{name}/backlinks")
async def get_backlinks(name: str) -> dict[str, Any]:
    """API-008：返回反链面板数据。"""

    store = _store()
    page = store.read_page(name)
    index = store.link_index()
    return {
        "items": [
            {"name": source_name, "title": _metadata_value(source, "title", source.name)}
            for source_name in index.back_links.get(page.name, [])
            if (source := store.read_page(source_name)) is not None
        ]
    }


@router.get("/pages/{name}/diff")
async def get_page_diff(name: str) -> dict[str, Any]:
    """API-009：返回当前工作区页面相对 git HEAD 的 unified diff。"""

    store = _store()
    page = store.read_page(name)
    process = subprocess.run(
        ["git", "diff", "--unified=3", "HEAD", "--", page.relative_path.as_posix()],
        cwd=store.vault,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    diff = process.stdout if process.returncode == 0 else ""
    return {"diff": diff}


@router.get("/pages/{name:path}")
async def get_page(name: str) -> dict[str, Any]:
    """API-005：返回页面详情。"""

    store = _store()
    page = store.read_page(name)
    return _page_detail(page, store.link_index(), store)


@router.put("/pages/{name:path}")
async def update_page(name: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """API-006：保存人工编辑，并强制标记 human_edited。"""

    request = PageUpdateRequest.parse(body)
    store = _store()
    current = store.read_page(name)
    updated = store.write_page(
        _draft_from_page(current, content=request.content, human_edited=True)
    )
    return _page_detail(updated, store.link_index(), store)


def _draft_from_page(
    page: Page,
    *,
    content: str | None = None,
    zone: str | None = None,
    human_edited: bool | None = None,
):
    """从现有页面构造可原子保存的草稿，保留不属于本次编辑的元数据。"""

    from llmwiki.workspace.store import PageDraft

    return PageDraft(
        name=page.name,
        title=_metadata_value(page, "title", page.name),
        page_type=_page_type(page),
        source_type=_source_type(page).value,
        zone=zone if zone is not None else _metadata_value(page, "zone", ""),
        content=page.content if content is None else content,
        human_edited=page.metadata.get("human_edited") is True
        if human_edited is None
        else human_edited,
        status=_page_status(page),
        origin_source=_metadata_value(page, "origin_source", ""),
        metadata=page.metadata,
    )
