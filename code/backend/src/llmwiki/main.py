"""应用装配：FastAPI + 静态托管 + 统一错误处理。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from llmwiki.config import config_store
from llmwiki.errors import AppError

VERSION = "0.1.0"

app = FastAPI(title="LLM Wiki", version=VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json")

# --- 路由注册 ---
from llmwiki.api import ask, compile, events, lint, pages, settings, sources, system  # noqa: E402

for module in (system, pages, sources, compile, ask, lint, settings, events):
    app.include_router(module.router)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.get("/api/system/health")
async def health() -> dict:
    """TASK-001 验收：返回版本、vault 状态、LLM 配置状态、队列状态。"""
    from llmwiki.jobs import job_queue  # 延迟导入避免循环

    settings = config_store.load()
    vault = Path(settings.vault_path) if settings.vault_path else None
    return {
        "version": VERSION,
        "vault": {
            "path": settings.vault_path,
            "initialized": bool(vault and vault.exists() and (vault / "wiki").exists()),
        },
        "llm": {
            "configured": config_store.llm_configured,
            "provider": settings.llm.provider,
            "model": settings.llm.model,
        },
        "jobs": {
            "running": job_queue.running,
            "queued": job_queue.queue_size,
            "current_job_id": job_queue.current_job_id,
        },
    }


# --- 静态托管（生产模式，frontend/dist 存在时） ---
_dist = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")


def run() -> None:
    """CLI 入口：uv run python -m llmwiki"""
    import socket

    import uvicorn

    port = 8765
    for p in range(8765, 8776):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                port = p
                break
    print(f"LLM Wiki v{VERSION} → http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    run()
