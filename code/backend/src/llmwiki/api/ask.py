"""问答接口（API-028 ~ API-032）。路由骨架，服务层由 Wave 3 实现。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["ask"])


@router.post("/ask")
async def ask(body: dict) -> dict:
    return {}


@router.post("/ask/{query_id}/save-as-page")
async def save_as_page(query_id: str) -> dict:
    return {}


@router.get("/queries")
async def list_queries(page: int = 1, size: int = 50) -> dict:
    return {"items": [], "total": 0}


@router.get("/queries/{query_id}")
async def get_query(query_id: str) -> dict:
    return {}


@router.delete("/queries/{query_id}")
async def delete_query(query_id: str) -> dict:
    return {}
