"""OpenAI-compatible Chat Completions 异步客户端。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from atlaswiki.config import LlmSettings, config_store
from atlaswiki.errors import AppError, ErrorCode

from .cost import estimate_tokens, record_usage, usage_from_response

_client: httpx.AsyncClient | None = None


def _settings() -> LlmSettings:
    return config_store.load().llm


def _require_settings() -> LlmSettings:
    settings = _settings()
    if not settings.api_key.strip():
        raise AppError(
            ErrorCode.LLM_NOT_CONFIGURED,
            "LLM API key 未配置",
            {"base_url": settings.base_url},
        )
    return settings


def _chat_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _create_client(settings: LlmSettings) -> httpx.AsyncClient:
    """创建共享 AsyncClient；独立出来便于测试替换 transport。"""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.timeout_s),
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )


async def get_client() -> httpx.AsyncClient:
    """返回进程内共享客户端。"""
    global _client
    if _client is None or _client.is_closed:
        _client = _create_client(_require_settings())
    return _client


async def close_client() -> None:
    """关闭共享客户端，通常由应用 shutdown 调用。"""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _request_payload(
    messages: Sequence[dict[str, Any]],
    *,
    model: str,
    temperature: float | None,
    json_mode: bool,
    stream: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "stream": stream,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def _map_http_status(status_code: int, response: httpx.Response) -> AppError:
    detail = response.text[:500]
    if status_code in (401, 402, 403):
        return AppError(
            ErrorCode.LLM_AUTH,
            "LLM 鉴权失败或余额不足",
            {"status_code": status_code, "detail": detail},
        )
    if status_code == 429:
        return AppError(
            ErrorCode.LLM_RATE_LIMIT,
            "LLM 请求被限流",
            {"status_code": status_code, "detail": detail},
        )
    return AppError(
        ErrorCode.VALIDATION,
        "LLM 端点返回错误",
        {"status_code": status_code, "detail": detail},
    )


def _content_from_response(response_json: dict[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AppError(
            ErrorCode.VALIDATION,
            "LLM 响应缺少 choices[0].message.content",
            {"response": response_json},
        ) from exc
    return "" if content is None else str(content)


async def complete(
    messages: Sequence[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
    operation: str = "llm",
    job_id: str | None = None,
) -> str:
    """调用 Chat Completions 并返回助手文本。"""
    settings = _require_settings()
    selected_model = model or settings.model
    payload = _request_payload(
        messages,
        model=selected_model,
        temperature=temperature,
        json_mode=json_mode,
        stream=False,
    )
    try:
        client = await get_client()
        response = await client.post(
            _chat_url(settings.base_url),
            json=payload,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )
        if response.status_code >= 400:
            raise _map_http_status(response.status_code, response)
        response.raise_for_status()
        response_json = response.json()
        content = _content_from_response(response_json)
    except httpx.TimeoutException as exc:
        raise AppError(
            ErrorCode.LLM_TIMEOUT,
            "LLM 请求超时",
            {"timeout_s": settings.timeout_s},
        ) from exc

    input_tokens, output_tokens = usage_from_response(response_json, list(messages), content)
    await record_usage(
        model=selected_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        operation=operation,
        job_id=job_id,
    )
    return content


async def _stream_usage_event(response_json: dict[str, Any]) -> int | None:
    """读取 OpenAI 流式 usage 事件的 completion_tokens。"""
    usage = response_json.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        return int(usage.get("completion_tokens", 0))
    except (TypeError, ValueError):
        return None


async def stream(
    messages: Sequence[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
    operation: str = "llm",
    job_id: str | None = None,
) -> AsyncIterator[str]:
    """流式调用 Chat Completions，逐段 yield content delta。"""
    settings = _require_settings()
    selected_model = model or settings.model
    payload = _request_payload(
        messages,
        model=selected_model,
        temperature=temperature,
        json_mode=json_mode,
        stream=True,
    )
    client = await get_client()
    response = await client.send(
        client.build_request(
            "POST",
            _chat_url(settings.base_url),
            json=payload,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        ),
        stream=True,
    )
    if response.status_code >= 400:
        await response.aread()
        error = _map_http_status(response.status_code, response)
        await response.aclose()
        raise error

    chunks: list[str] = []
    completion_tokens: int | None = None
    try:
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            usage_tokens = await _stream_usage_event(event)
            if usage_tokens is not None:
                completion_tokens = usage_tokens
            try:
                delta = event["choices"][0]["delta"].get("content")
            except (KeyError, IndexError, TypeError):
                continue
            if delta:
                text = str(delta)
                chunks.append(text)
                yield text
    except httpx.TimeoutException as exc:
        raise AppError(
            ErrorCode.LLM_TIMEOUT,
            "LLM 流式响应超时",
            {"timeout_s": settings.timeout_s},
        ) from exc
    finally:
        await response.aclose()

    output = "".join(chunks)
    input_tokens = estimate_tokens(json.dumps(messages, ensure_ascii=False, sort_keys=True))
    output_tokens = completion_tokens if completion_tokens is not None else estimate_tokens(output)
    await record_usage(
        model=selected_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        operation=operation,
        job_id=job_id,
    )
