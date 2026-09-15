"""素材接口（API-014 ~ API-023）。路由骨架，服务层由 G2 实现。"""

from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
async def list_sources(
    status: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> dict:
    return {"items": [], "total": 0, "counts": {}}


@router.post("/web")
async def import_web(body: dict) -> dict:
    return {}


@router.post("/note")
async def import_note(body: dict) -> dict:
    return {}


@router.post("/pdf")
async def import_pdf(body: dict) -> dict:
    return {}


@router.get("/{source_id}")
async def get_source(source_id: str) -> dict:
    return {}


@router.patch("/{source_id}")
async def update_source(source_id: str, body: dict) -> dict:
    return {}


@router.delete("/{source_id}")
async def delete_source(source_id: str) -> dict:
    return {}
