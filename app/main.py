"""FastAPI 服务 —— LLM Wiki 的接口层。

核心操作只有三个，和 Karpathy 的原始构想一致：
    ingest（收录）→ 落 raw/，然后编译进 wiki/
    query （查询）→ LLM 读索引 + 读页面，综合作答
    lint  （体检）→ 找出矛盾、孤儿页、缺失引用
"""

from __future__ import annotations

import json
import re
import shutil
import traceback
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, compiler, config, lint as lint_mod, schema, vault
from .ingest import SOURCE_LABELS, ingest_file, ingest_one, save_to_raw
from .ingest.common import IngestError
from .textutil import clip

app = FastAPI(title="LLM Wiki", version="0.2.0")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.exception_handler(vault.VaultError)
async def _vault_error_handler(request: Request, exc: vault.VaultError) -> JSONResponse:
    """路径越界、非法路径等 vault 主动抛出的错误 → 400，而不是 500。

    vault 的路径校验是一道有意设置的防线，被它拒绝说明**请求本身不合法**，
    不该表现成服务端崩溃（前端只会看到无信息量的 Internal Server Error，
    日志里却多出一条 traceback）。
    """
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.on_event("startup")
def _startup() -> None:
    config.write_default_config()
    vault.ensure_vault()


# --------------------------------------------------------------------------- #
# 请求模型
# --------------------------------------------------------------------------- #

class IngestRequest(BaseModel):
    input: str = Field("", description="链接或文本，支持多行")
    tags: list[str] = Field(default_factory=list)


class CompileRequest(BaseModel):
    paths: list[str] | None = Field(None, description="要编译的 raw 素材路径；留空表示编译全部未编译素材")
    all: bool = False


class AskRequest(BaseModel):
    question: str
    history: list[dict[str, str]] = Field(default_factory=list)
    file_answer: bool = False


class PageSaveRequest(BaseModel):
    content: str
    title: str | None = None


class ConfigUpdateRequest(BaseModel):
    llm: dict[str, Any] | None = None
    ingest: dict[str, Any] | None = None
    fetch: dict[str, Any] | None = None
    lint: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# SSE
# --------------------------------------------------------------------------- #

def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _stream(gen_factory) -> StreamingResponse:
    async def generator() -> AsyncIterator[str]:
        try:
            async for event in gen_factory():
                yield _sse(event)
        except IngestError as exc:
            yield _sse({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# --------------------------------------------------------------------------- #
# 基础信息
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health() -> dict[str, Any]:
    from .ingest.common import ytdlp_available

    cfg = config.load_config()
    return {
        "ok": True,
        "version": app.version,
        "llm_ready": config.llm_ready(),
        "llm_model": cfg["llm"].get("model", ""),
        "llm_base_url": cfg["llm"].get("base_url", ""),
        "ytdlp": ytdlp_available(),
        "source_labels": SOURCE_LABELS,
        "paths": config.describe(),
    }


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    data = vault.stats()
    data["llm_ready"] = config.llm_ready()
    data["pending_raw"] = len(pending_raw())
    return data


@app.get("/api/log")
def get_log(limit: int = Query(60, ge=1, le=500)) -> dict[str, Any]:
    return {"entries": vault.read_log(limit=limit)}


# --------------------------------------------------------------------------- #
# 收录
# --------------------------------------------------------------------------- #

def _pending_set() -> set[str]:
    used: set[str] = set()
    for page in vault.list_pages(with_backlinks=False):
        for src in page.frontmatter.get("sources") or []:
            used.add(str(src))
    return used


def pending_raw() -> list[dict[str, Any]]:
    used = _pending_set()
    return [item for item in vault.list_raw() if item["path"] not in used]


@app.get("/api/raw")
def list_raw(only_pending: bool = False) -> dict[str, Any]:
    used = _pending_set()
    items = vault.list_raw()
    for item in items:
        item["pending"] = item["path"] not in used
    if only_pending:
        items = [item for item in items if item["pending"]]
    return {"items": items, "total": len(items)}


@app.get("/api/raw/content")
def read_raw(path: str = Query(...)) -> dict[str, Any]:
    try:
        text = vault.read_raw(path)
    except vault.VaultError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    meta, body = vault.parse_frontmatter(text)
    return {"path": path, "frontmatter": meta, "body": body}


@app.post("/api/ingest")
def ingest(payload: IngestRequest) -> dict[str, Any]:
    from .ingest import split_inputs

    items = split_inputs(payload.input)
    if not items:
        raise HTTPException(status_code=400, detail="输入为空")
    if len(items) > 30:
        raise HTTPException(status_code=400, detail="一次最多 30 条，请分批提交")

    results: list[dict[str, Any]] = []
    for item in items:
        preview_text = item if len(item) <= 90 else item[:90] + "…"
        try:
            result = ingest_one(item, tags=payload.tags)
            raw_path = save_to_raw(result)
            results.append(
                {
                    "ok": True,
                    "input": preview_text,
                    "title": result.title,
                    "source_type": result.source_type,
                    "source_type_label": SOURCE_LABELS.get(result.source_type, result.source_type),
                    "source_url": result.source_url,
                    "author": result.author,
                    "raw_path": raw_path,
                    "chars": len(result.content_md),
                    "tags": result.tags[:10],
                    "warnings": result.warnings,
                }
            )
        except IngestError as exc:
            results.append({"ok": False, "input": preview_text, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            results.append({"ok": False, "input": preview_text, "error": f"{type(exc).__name__}: {exc}"})

    ok_paths = [r["raw_path"] for r in results if r.get("ok")]
    return {
        "results": results,
        "ok_count": len(ok_paths),
        "fail_count": len(results) - len(ok_paths),
        "raw_paths": ok_paths,
        "pending_raw": len(pending_raw()),
        # 由 config.yaml 的 ingest.auto_compile 决定前端是否自动接着编译
        "auto_compile": config.auto_compile(),
    }


@app.post("/api/ingest/upload")
async def ingest_upload(
    files: list[UploadFile] = File(...),
    tags: str = Query(""),
) -> dict[str, Any]:
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    config.ensure_dirs()
    results: list[dict[str, Any]] = []

    for upload in files:
        name = upload.filename or "unnamed"
        safe = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name)
        target = config.UPLOAD_DIR / safe
        try:
            with target.open("wb") as handle:
                shutil.copyfileobj(upload.file, handle)
        except Exception as exc:  # noqa: BLE001
            results.append({"ok": False, "input": name, "error": f"保存失败：{exc}"})
            continue
        finally:
            await upload.close()

        try:
            result = ingest_file(target, filename=name, tags=tag_list)
            raw_path = save_to_raw(result)
            results.append(
                {
                    "ok": True,
                    "input": name,
                    "title": result.title,
                    "source_type": result.source_type,
                    "source_type_label": SOURCE_LABELS.get(result.source_type, result.source_type),
                    "raw_path": raw_path,
                    "chars": len(result.content_md),
                    "tags": result.tags[:10],
                    "warnings": result.warnings,
                }
            )
        except IngestError as exc:
            results.append({"ok": False, "input": name, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            results.append({"ok": False, "input": name, "error": f"{type(exc).__name__}: {exc}"})

    ok_paths = [r["raw_path"] for r in results if r.get("ok")]
    return {
        "results": results,
        "ok_count": len(ok_paths),
        "fail_count": len(results) - len(ok_paths),
        "raw_paths": ok_paths,
        "pending_raw": len(pending_raw()),
        # 由 config.yaml 的 ingest.auto_compile 决定前端是否自动接着编译
        "auto_compile": config.auto_compile(),
    }


# --------------------------------------------------------------------------- #
# 编译（LLM Wiki 的核心步骤）
# --------------------------------------------------------------------------- #

async def _compile_one(raw_path: str, title: str) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "compile_start", "raw_path": raw_path, "title": title}

    if not config.llm_ready():
        yield {"type": "step", "tool": "compiler", "description": "未配置大模型，使用确定性编译器", "args": {}}
        try:
            result = compiler.compile_source(raw_path, progress=lambda msg: None)
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "message": f"编译失败：{exc}"}
            return
        yield {
            "type": "compile_done",
            "raw_path": raw_path,
            "source_page": result["source_page"],
            "created": result["created"],
            "mode": "deterministic",
        }
        return

    slug = vault.slug_of(raw_path)
    prompt = schema.render_ingest_prompt(raw_path, title, slug)
    pages: list[str] = []
    text_parts: list[str] = []
    try:
        async for event in agent.stream_agent(prompt):
            if event["type"] == "token":
                text_parts.append(event["text"])
                yield {"type": "token", "text": event["text"]}
            elif event["type"] == "retract":
                joined = "".join(text_parts)
                keep = max(0, len(joined) - int(event.get("chars", 0)))
                text_parts = [joined[:keep]]
                yield {"type": "retract", "chars": event.get("chars", 0)}
            elif event["type"] == "step":
                yield event
            elif event["type"] == "pages":
                pages = event.get("pages", [])
            elif event["type"] == "error":
                yield event
    except agent.AgentError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    # 结构不变量不能依赖模型自觉：SCHEMA 提示词里虽然让模型自己调 rebuild_index，
    # 但它可能忘记（或被中途打断）。索引是纯派生数据，这里无条件重建一次兜底，
    # 保证新写的页面一定被 index.md 收录。
    vault.rebuild_index()
    vault.append_log("ingest", f"{title} → {len(pages)} 个页面（LLM 编译）")
    yield {
        "type": "compile_done",
        "raw_path": raw_path,
        "source_page": pages[0] if pages else "",
        "created": pages,
        "mode": "llm",
    }


@app.post("/api/compile")
def compile_many(payload: CompileRequest) -> StreamingResponse:
    if payload.paths:
        targets = [{"path": p, "title": vault.slug_of(p)} for p in payload.paths]
    else:
        items = vault.list_raw() if payload.all else pending_raw()
        targets = [{"path": i["path"], "title": i["title"]} for i in items]

    if not targets:
        async def empty() -> AsyncIterator[dict[str, Any]]:
            yield {"type": "notice", "message": "没有需要编译的素材"}
        return _stream(empty)

    raw_lookup = {item["path"]: item["title"] for item in vault.list_raw()}
    for target in targets:
        target["title"] = raw_lookup.get(target["path"], target["title"])

    async def generator() -> AsyncIterator[dict[str, Any]]:
        yield {"type": "batch_start", "count": len(targets), "llm": config.llm_ready()}
        for index, target in enumerate(targets, start=1):
            yield {"type": "batch_progress", "index": index, "total": len(targets), "title": target["title"]}
            async for event in _compile_one(target["path"], target["title"]):
                yield event
        if config.llm_ready():
            vault.rebuild_index()
        yield {"type": "batch_done", "count": len(targets)}

    return _stream(generator)


# --------------------------------------------------------------------------- #
# 浏览
# --------------------------------------------------------------------------- #

@app.get("/api/pages")
def list_pages(kind: str | None = None, q: str | None = None) -> dict[str, Any]:
    pages = vault.list_pages(with_backlinks=True)
    if kind:
        pages = [p for p in pages if p.kind == kind]
    if q:
        ql = q.strip().lower()
        pages = [
            p
            for p in pages
            if ql in p.title.lower() or ql in p.body.lower() or ql in str(p.frontmatter.get("summary", "")).lower()
        ]
    pages.sort(key=lambda p: (p.kind, p.title))
    return {
        "items": [p.to_dict(with_body=False) for p in pages],
        "total": len(pages),
        "by_kind": _by_kind(pages),
    }


def _by_kind(pages: list[vault.Page]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for page in pages:
        counts[page.kind] = counts.get(page.kind, 0) + 1
    return counts


@app.get("/api/page")
def get_page(path: str = Query(...)) -> dict[str, Any]:
    # 所有页面接口都先规范化路径，容忍调用方写成 wiki/xxx.md（见 vault.normalize_rel）
    page = vault.read_page(vault.normalize_rel(path))
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    # read_page 只读单个文件，不会计算反向链接（那是 list_pages 的职责），
    # 所以这里要拿一份带 backlinks 的全量页面，否则反向链接永远是空的。
    pages = vault.list_pages(with_backlinks=True)
    by_path = {p.rel_path: p for p in pages}
    link_map = vault.build_link_map(pages)

    resolved = []
    for link in page.links:
        target = vault.resolve_link(link, link_map)
        resolved.append({"raw": link, "path": target, "exists": bool(target)})

    backlink_rels = (by_path.get(page.rel_path).backlinks if by_path.get(page.rel_path) else [])
    backlinks = []
    for rel in backlink_rels:
        other = by_path.get(rel)
        if other:
            backlinks.append({"path": other.rel_path, "title": other.title, "kind": other.kind})

    data = page.to_dict(with_body=True)
    data["backlinks"] = backlink_rels
    data["resolved_links"] = resolved
    data["backlink_pages"] = backlinks
    return data


@app.put("/api/page")
def save_page(payload: PageSaveRequest, path: str = Query(...)) -> dict[str, Any]:
    rel = vault.normalize_rel(path)
    page = vault.write_page(rel, payload.content, title=payload.title)
    # 可能是新建页面：页面集合变了就得重建索引，否则它不会被 index.md 收录
    vault.rebuild_index()
    vault.append_log("edit", f"人工编辑 {rel}")
    return page.to_dict(with_body=True)


@app.get("/api/page/raw")
def get_page_raw(path: str = Query(...)) -> FileResponse:
    page = vault.read_page(vault.normalize_rel(path))
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    return FileResponse(page.path, media_type="text/markdown", filename=page.path.name)


@app.delete("/api/page")
def delete_page(path: str = Query(...)) -> dict[str, Any]:
    rel = vault.normalize_rel(path)
    if not vault.delete_page(rel):
        raise HTTPException(status_code=404, detail="页面不存在")
    # 页面没了，索引必须跟着重建，否则 index.md 会留下指向已删页面的失效链接
    vault.rebuild_index()
    vault.append_log("edit", f"删除 {rel}（已移入 .trash）")
    return {"ok": True, "path": rel}


@app.get("/api/index")
def get_index() -> dict[str, Any]:
    return {"content": vault.read_index()}


@app.post("/api/index/rebuild")
def rebuild_index() -> dict[str, Any]:
    content = vault.rebuild_index()
    return {"ok": True, "content": content}


@app.get("/api/graph")
def graph() -> dict[str, Any]:
    pages = vault.list_pages(with_backlinks=True)
    link_map = vault.build_link_map(pages)
    nodes = [
        {
            "id": p.rel_path,
            "title": p.title,
            "kind": p.kind,
            "kind_label": vault.KIND_LABELS.get(p.kind, p.kind),
            "degree": len(p.links) + len(p.backlinks),
            "size": len(p.body),
        }
        for p in pages
    ]
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for page in pages:
        for link in page.links:
            target = vault.resolve_link(link, link_map)
            if not target or target == page.rel_path:
                continue
            key = (page.rel_path, target)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"source": page.rel_path, "target": target})
    return {"nodes": nodes, "edges": edges}


@app.get("/api/search")
def search(q: str = Query(...), kind: str | None = None, limit: int | None = None) -> dict[str, Any]:
    # limit 留空时由 config.yaml 的 search.max_results 决定
    return {"query": q, "results": vault.search_wiki(q, limit=limit, kind=kind)}


# --------------------------------------------------------------------------- #
# 查询（LLM 读 wiki 作答）
# --------------------------------------------------------------------------- #

@app.post("/api/ask")
def ask(payload: AskRequest) -> StreamingResponse:
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")

    async def generator() -> AsyncIterator[dict[str, Any]]:
        if not config.llm_ready():
            yield {
                "type": "error",
                "message": "未配置大模型 API Key，无法基于 wiki 综合作答。请到「设置」里填写 llm.api_key。",
            }
            yield {
                "type": "notice",
                "message": "你也可以在左侧浏览页面，或用搜索框做关键词检索。",
            }
            return

        answer_parts: list[str] = []
        prompt = schema.render_query_prompt(question)
        async for event in agent.stream_agent(prompt, history=payload.history):
            if event["type"] == "token":
                answer_parts.append(event["text"])
            yield event

        answer = "".join(answer_parts).strip()
        if payload.file_answer and answer:
            slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", question)[:40].strip("-") or "qa"
            path = f"analyses/{slug}.md"
            vault.write_page(
                path,
                f"# {question}\n\n> 由 LLM 基于知识库回答后归档。\n\n{answer}",
                title=question[:80],
                frontmatter={"type": "analysis", "tags": ["问答归档"], "summary": clip(answer, 100)},
            )
            vault.rebuild_index()
            vault.append_log("query", f"归档问答：{question[:60]} → {path}")
            yield {"type": "filed", "path": path}

    return _stream(generator)


# --------------------------------------------------------------------------- #
# Lint
# --------------------------------------------------------------------------- #

@app.get("/api/lint")
def structural_lint() -> dict[str, Any]:
    return lint_mod.structural_lint()


@app.post("/api/lint/save")
def save_lint_report() -> dict[str, Any]:
    report = lint_mod.structural_lint()
    path = lint_mod.save_report(report)
    return {"ok": True, "path": path, "issues": report["issues"]}


@app.post("/api/lint/llm")
def llm_lint() -> StreamingResponse:
    async def generator() -> AsyncIterator[dict[str, Any]]:
        if not config.llm_ready():
            yield {"type": "error", "message": "未配置大模型，无法做语义体检。可先使用结构体检。"}
            return
        async for event in agent.stream_agent(schema.LINT_PROMPT):
            yield event

    return _stream(generator)


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #

def _mask(cfg: dict[str, Any]) -> dict[str, Any]:
    safe = json.loads(json.dumps(cfg, ensure_ascii=False))
    key = str(safe.get("llm", {}).get("api_key") or "")
    safe["llm"]["api_key_set"] = bool(key)
    if key:
        safe["llm"]["api_key_masked"] = (key[:4] + "…" + key[-4:]) if len(key) > 10 else "已设置"
    safe["llm"].pop("api_key", None)
    safe["paths"] = config.describe()
    return safe


@app.get("/api/config")
def read_config() -> dict[str, Any]:
    return _mask(config.load_config())


@app.put("/api/config")
def write_config(payload: ConfigUpdateRequest) -> dict[str, Any]:
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items() if v}
    llm_update = dict(updates.get("llm") or {})
    key = str(llm_update.get("api_key") or "")
    if not key or "*" in key or "…" in key:
        llm_update.pop("api_key", None)
    if llm_update:
        updates["llm"] = llm_update
    else:
        updates.pop("llm", None)
    cfg = config.save_config(updates) if updates else config.load_config(reload=True)
    return _mask(cfg)


# --------------------------------------------------------------------------- #
# 静态资源
# --------------------------------------------------------------------------- #

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
