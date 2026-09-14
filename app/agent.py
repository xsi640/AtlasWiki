"""LLM Agent —— 让模型直接读写 wiki 文件，而不是走检索。

这就是 LLM Wiki 与 RAG 的分界线：
  RAG   = 切块 → 向量 → 查询时召回 → 生成
  LLM Wiki = 模型拿着 list/read/write/search 工具，自己读索引、读页面、写页面
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from . import config, schema, vault

MAX_TOOL_RESULT_CHARS = 14000


class AgentError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# 工具定义
# --------------------------------------------------------------------------- #

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_wiki",
            "description": "列出 wiki 中的全部页面（路径、标题、类型、摘要）。先用它建立全局印象。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["sources", "entities", "concepts", "analyses", "root"],
                        "description": "只列出某一类页面，留空则列出全部",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_wiki",
            "description": "读取一个 wiki 页面的完整内容（含 frontmatter）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，如 concepts/rag.md 或 index.md"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_wiki",
            "description": "创建或覆盖一个 wiki 页面。整页替换，请把要保留的旧内容一起写进去。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，如 concepts/rag.md"},
                    "content": {"type": "string", "description": "页面正文（Markdown），可含 YAML frontmatter"},
                    "title": {"type": "string", "description": "页面标题，留空则从正文一级标题推断"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
                    "summary": {"type": "string", "description": "一句话摘要，会出现在索引中"},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "支撑本页的原始素材路径，如 raw/xxx.md",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_wiki",
            "description": "对已有页面做精确字符串替换。适合小改动，比整页重写更省。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string", "description": "要替换的原文，必须与文件中完全一致"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean", "description": "是否替换全部出现"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_wiki",
            "description": "在页面末尾追加内容（页面不存在则创建）。适合给概念页补一个新小节。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_wiki",
            "description": "在 wiki 全文里搜索关键词，返回命中的页面与上下文片段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "空格分隔的关键词，全部命中才算匹配"},
                    "kind": {"type": "string", "description": "限定页面类型，可留空"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_raw",
            "description": "列出 raw/ 里的原始素材（路径、标题、来源、字数）。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_raw",
            "description": "读取原始素材全文。这是真相来源，不要修改它。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "如 raw/xxx.md"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rebuild_index",
            "description": "根据当前所有页面确定性重建 index.md。想省 token 时用它代替手写索引。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_log",
            "description": "往 log.md 追加一条操作记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "description": "ingest / query / lint / edit"},
                    "message": {"type": "string"},
                },
                "required": ["kind", "message"],
            },
        },
    },
]


# --------------------------------------------------------------------------- #
# 工具执行
# --------------------------------------------------------------------------- #

def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n…（内容过长，已截断，原长 {len(text)} 字符）"


def _resolve_wiki_path(raw_path: str) -> str:
    """让模型可以写 'concepts/rag' 或 'rag' 这类简写。"""
    rel = vault.normalize_rel(raw_path)
    if vault.page_exists(rel):
        return rel
    if "/" not in rel:
        for kind in ("concepts", "entities", "sources", "analyses"):
            candidate = f"{kind}/{rel}"
            if vault.page_exists(candidate):
                return candidate
    return rel


def execute_tool(name: str, args: dict[str, Any]) -> tuple[str, str]:
    """执行一个工具，返回 (给模型看的结果, 给 UI 看的一句话描述)。"""
    args = args or {}

    if name == "list_wiki":
        kind = args.get("kind") or None
        pages = [p for p in vault.list_pages(with_backlinks=True) if not kind or p.kind == kind]
        if not pages:
            return "wiki 目前没有任何页面。", "列出 wiki 页面（空）"
        lines = []
        for page in sorted(pages, key=lambda p: (p.kind, p.title)):
            summary = str(page.frontmatter.get("summary") or "").strip()
            back = f" ←{len(page.backlinks)}" if page.backlinks else ""
            lines.append(f"- {page.rel_path} | {page.kind} | 《{page.title}》{back} | {summary}")
        return "\n".join(lines), f"列出 {len(pages)} 个页面"

    if name == "read_wiki":
        rel = _resolve_wiki_path(str(args.get("path", "")))
        page = vault.read_page(rel)
        if not page:
            hint = ""
            near = [p.rel_path for p in vault.list_pages(with_backlinks=False) if page is None and p.slug and p.slug in rel]
            if near:
                hint = f" 你是不是想找：{', '.join(near[:5])}"
            return f"页面不存在：{rel}。{hint}", f"读取失败 {rel}"
        meta = json.dumps(page.frontmatter, ensure_ascii=False)
        content = f"路径：{page.rel_path}\nfrontmatter：{meta}\n出链：{page.links}\n入链：{page.backlinks}\n\n{page.body}"
        return _truncate(content, MAX_TOOL_RESULT_CHARS), f"读取 {rel}"

    if name == "write_wiki":
        rel = vault.normalize_rel(str(args.get("path", "")))
        if not rel or rel == ".md":
            return "path 不能为空", "写入失败：路径为空"
        existed = vault.page_exists(rel)
        frontmatter: dict[str, Any] = {"type": vault.kind_of(rel).rstrip("s")}
        if args.get("tags"):
            frontmatter["tags"] = args["tags"]
        if args.get("summary"):
            frontmatter["summary"] = args["summary"]
        if args.get("sources"):
            frontmatter["sources"] = args["sources"]
        page = vault.write_page(rel, str(args.get("content", "")), title=args.get("title"), frontmatter=frontmatter)
        verb = "更新" if existed else "新建"
        return (
            f"已{verb} {page.rel_path}（{len(page.body)} 字符，标题《{page.title}》）",
            f"{verb} {page.rel_path}",
        )

    if name == "edit_wiki":
        rel = _resolve_wiki_path(str(args.get("path", "")))
        ok, message = vault.edit_page(
            rel,
            str(args.get("old_string", "")),
            str(args.get("new_string", "")),
            bool(args.get("replace_all")),
        )
        return message, ("编辑 " + rel if ok else f"编辑失败 {rel}")

    if name == "append_wiki":
        rel = vault.normalize_rel(str(args.get("path", "")))
        page = vault.append_page(rel, str(args.get("content", "")))
        return f"已追加到 {page.rel_path}（现 {len(page.body)} 字符）", f"追加 {page.rel_path}"

    if name == "search_wiki":
        results = vault.search_wiki(str(args.get("query", "")), kind=args.get("kind") or None)
        if not results:
            return "没有匹配的页面。", f"搜索「{args.get('query', '')}」（无结果）"
        blocks = []
        for item in results[:12]:
            hits = "\n".join(f"  L{hit['line']}: {hit['text'][:220]}" for hit in item["hits"][:3])
            blocks.append(f"### {item['path']} 《{item['title']}》\n{hits}")
        return _truncate("\n\n".join(blocks), MAX_TOOL_RESULT_CHARS), f"搜索「{args.get('query', '')}」命中 {len(results)} 页"

    if name == "list_raw":
        items = vault.list_raw()
        if not items:
            return "raw/ 目录是空的。", "列出原始素材（空）"
        lines = [f"- {i['path']} | {i['title']} | {i['source_type']} | {i['chars']} 字符" for i in items]
        return "\n".join(lines), f"列出 {len(items)} 个素材"

    if name == "read_raw":
        try:
            text = vault.read_raw(str(args.get("path", "")))
        except vault.VaultError as exc:
            return str(exc), f"读取素材失败"
        return _truncate(text, config.max_source_chars()), f"读取素材 {args.get('path', '')}"

    if name == "rebuild_index":
        content = vault.rebuild_index()
        return f"index.md 已重建，共 {content.count('- [[')} 条目录项。", "重建索引"

    if name == "append_log":
        vault.append_log(str(args.get("kind", "note")), str(args.get("message", "")))
        return "日志已追加。", "记录日志"

    return f"未知工具：{name}", f"未知工具 {name}"


# --------------------------------------------------------------------------- #
# Agent 循环
# --------------------------------------------------------------------------- #

def _endpoint() -> tuple[str, dict[str, str]]:
    cfg = config.load_config()["llm"]
    if not cfg.get("api_key"):
        raise AgentError("尚未配置大模型 API Key（config.yaml → llm.api_key）")
    base = str(cfg["base_url"]).rstrip("/")
    headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
    return f"{base}/chat/completions", headers


async def stream_agent(
    task_prompt: str,
    *,
    history: list[dict[str, str]] | None = None,
    max_rounds: int | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """运行 agent 循环，产出事件流。

    事件类型：
      step       —— 一次工具调用及其结果摘要
      token      —— 助手最终回答的增量文本
      retract    —— 撤回上一轮已流出的文本（模型先说后调工具的情况）
      pages      —— 本次改动过的页面列表
      error/done
    """
    cfg = config.load_config()["llm"]
    url, headers = _endpoint()
    rounds_limit = int(max_rounds or cfg.get("max_tool_rounds", 24))
    tool_defs = tools if tools is not None else TOOLS

    messages: list[dict[str, Any]] = [{"role": "system", "content": schema.system_prompt()}]
    for turn in (history or [])[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": task_prompt})

    touched: list[str] = []
    timeout = httpx.Timeout(connect=20.0, read=600.0, write=60.0, pool=20.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for round_index in range(rounds_limit):
            payload = {
                "model": cfg["model"],
                "messages": messages,
                "temperature": float(cfg.get("temperature", 0.2)),
                "max_tokens": int(cfg.get("max_tokens", 4096)),
                "stream": True,
            }
            if tool_defs:
                payload["tools"] = tool_defs
                payload["tool_choice"] = "auto"

            content_parts: list[str] = []
            streamed_chars = 0
            tool_calls: dict[int, dict[str, Any]] = {}

            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "ignore")[:800]
                    raise AgentError(f"模型接口返回 {response.status_code}：{body}")
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        parsed = json.loads(data)
                    except Exception:
                        continue
                    choices = parsed.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content")
                    if piece:
                        content_parts.append(piece)
                        streamed_chars += len(piece)
                        yield {"type": "token", "text": piece}
                    for call in delta.get("tool_calls") or []:
                        index = call.get("index", 0)
                        slot = tool_calls.setdefault(
                            index, {"id": "", "name": "", "arguments": ""}
                        )
                        if call.get("id"):
                            slot["id"] = call["id"]
                        function = call.get("function") or {}
                        if function.get("name"):
                            slot["name"] = function["name"]
                        if function.get("arguments"):
                            slot["arguments"] += function["arguments"]

            if not tool_calls:
                if not content_parts:
                    yield {"type": "token", "text": "（模型没有返回内容）"}
                break

            # 模型先说了话又调工具 —— 把已经流出的文字撤回
            if streamed_chars:
                yield {"type": "retract", "chars": streamed_chars}

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": "".join(content_parts) or None,
                "tool_calls": [
                    {
                        "id": slot["id"] or f"call_{index}",
                        "type": "function",
                        "function": {"name": slot["name"], "arguments": slot["arguments"] or "{}"},
                    }
                    for index, slot in sorted(tool_calls.items())
                ],
            }
            messages.append(assistant_message)

            for call in assistant_message["tool_calls"]:
                fn = call["function"]
                try:
                    args = json.loads(fn["arguments"] or "{}")
                except Exception:
                    args = {}
                try:
                    result, description = execute_tool(fn["name"], args)
                except Exception as exc:  # noqa: BLE001
                    result, description = f"工具执行失败：{type(exc).__name__}: {exc}", f"{fn['name']} 失败"
                if fn["name"] in ("write_wiki", "edit_wiki", "append_wiki"):
                    path = str(args.get("path") or "")
                    if path and path not in touched:
                        touched.append(path)
                yield {"type": "step", "tool": fn["name"], "description": description, "args": args}
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        else:
            yield {"type": "step", "tool": "limit", "description": f"达到工具调用上限（{rounds_limit} 轮）", "args": {}}

    yield {"type": "pages", "pages": touched}
    yield {"type": "done", "rounds": rounds_limit}


async def run_agent(task_prompt: str, **kwargs: Any) -> dict[str, Any]:
    """非流式版本，返回 {text, steps, pages}。"""
    text_parts: list[str] = []
    steps: list[dict[str, Any]] = []
    pages: list[str] = []
    async for event in stream_agent(task_prompt, **kwargs):
        if event["type"] == "token":
            text_parts.append(event["text"])
        elif event["type"] == "retract":
            joined = "".join(text_parts)
            keep = max(0, len(joined) - int(event.get("chars", 0)))
            text_parts = [joined[:keep]]
        elif event["type"] == "step":
            steps.append(event)
        elif event["type"] == "pages":
            pages = event.get("pages", [])
    return {"text": "".join(text_parts).strip(), "steps": steps, "pages": pages}
