"""页面与图谱接口（API-004 ~ API-013）。路由骨架，服务层由 Wave 2 实现。"""

from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api", tags=["pages"])


@router.get("/pages")
async def list_pages(
    zone: str | None = None,
    type: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> dict:
    """页面列表（TASK-021 实现）。"""
    return {"items": [], "total": 0}


@router.get("/pages/{name:path}")
async def get_page(name: str) -> dict:
    """页面详情（TASK-021 实现）。"""
    return {}


@router.get("/graph")
async def get_graph(
    zone: str | None = None,
    depth: int = Query(1, ge=1, le=2),
    center: str | None = None,
) -> dict:
    """图谱数据（TASK-022 实现）。"""
    return {"nodes": [], "edges": [], "truncated": False, "node_count": 0, "edge_count": 0}


@router.get("/zones")
async def list_zones() -> list[dict]:
    """分区列表（TASK-022 实现）。"""
    return []


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> dict:
    """全局搜索（TASK-022 实现）。"""
    return {"items": [], "total": 0, "query": q}
