"""应用装配：FastAPI + 路由注册 + 静态托管 + 统一错误处理。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from llmwiki.config import config_store
from llmwiki.errors import AppError

VERSION = "0.1.0"

app = FastAPI(title="LLM Wiki", version=VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json")


# --- 统一错误处理 ---
@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


# --- 健康检查 ---
@app.get("/api/system/health")
async def health() -> dict:
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


# --- 路由注册（必须在静态托管之前） ---
from llmwiki.api import ask, events, lint, pages, settings, sources, system  # noqa: E402
from llmwiki.api import compile as _compile  # noqa: E402

for module in (system, pages, sources, _compile, ask, lint, settings, events):
    app.include_router(module.router)

# --- 静态托管（最后挂载，避免拦截 /api 路由） ---
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
