"""TASK-006 LLM client and cost accounting acceptance tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from llmwiki.config import LlmSettings, Settings, config_store
from llmwiki.errors import AppError, ErrorCode
from llmwiki.llm import (
    clear_custom_pricing,
    close_client,
    complete,
    get_cost_summary,
    get_costs,
    stream,
)
from llmwiki.llm import client as llm_client


def install_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, api_key: str = "test-key") -> Settings:
    settings = Settings(
        vault_path=str(tmp_path),
        llm=LlmSettings(
            api_key=api_key,
            base_url="https://llm.example/v1",
            model="gpt-4o-mini",
            timeout_s=2,
        ),
    )
    monkeypatch.setattr(config_store, "_cache", settings)
    return settings


@pytest.fixture
async def llm_mock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], dict[str, Any]]:
    """注入 MockTransport 并返回请求/响应捕获容器。"""
    install_settings(tmp_path, monkeypatch)
    captured: dict[str, Any] = {}

    def use_handler(handler: Callable[[httpx.Request], httpx.Response]) -> dict[str, Any]:
        def wrapped(request: httpx.Request) -> httpx.Response:
            captured["request"] = request
            captured["payload"] = json.loads(request.content.decode("utf-8"))
            captured["response"] = response = handler(request)
            return response

        transport = httpx.MockTransport(wrapped)
        monkeypatch.setattr(
            llm_client,
            "_create_client",
            lambda _settings: httpx.AsyncClient(transport=transport),
        )
        return captured

    yield use_handler
    await close_client()


async def test_complete_calls_openai_compatible_endpoint_and_records_cost(llm_mock) -> None:
    captured = llm_mock(
        lambda _request: httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "回答完成"}}],
                "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
            },
        )
    )
    messages = [
        {"role": "system", "content": "你是知识整理器"},
        {"role": "user", "content": "总结这个概念"},
    ]

    result = await complete(messages, temperature=0.1, operation="compile", job_id="job-1")

    assert result == "回答完成"
    request = captured["request"]
    assert str(request.url) == "https://llm.example/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    assert captured["payload"] == {
        "model": "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.1,
        "stream": False,
    }

    records = await get_costs()
    assert len(records) == 1
    assert records[0] == {
        **records[0],
        "operation": "compile",
        "model": "gpt-4o-mini",
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "input_cost": 0.15,
        "output_cost": 0.6,
        "cost": 0.75,
        "currency": "USD",
        "pricing_source": "builtin",
        "job_id": "job-1",
    }
    summary = await get_cost_summary()
    assert summary["total"] == 0.75
    assert summary["by_operation"] == [{"operation": "compile", "cost": 0.75, "calls": 1}]


async def test_stream_yields_deltas_and_records_estimated_cost(llm_mock) -> None:
    llm_mock(
        lambda _request: httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            content=(
                b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
                b"data: [DONE]\n\n"
            ),
        )
    )

    chunks = [chunk async for chunk in stream([{"role": "user", "content": "hi"}], json_mode=False)]

    assert chunks == ["Hel", "lo"]
    records = await get_costs()
    assert len(records) == 1
    assert records[0]["input_tokens"] > 0
    assert records[0]["output_tokens"] == 2
    assert records[0]["cost"] > 0


async def test_json_mode_sends_response_format(llm_mock) -> None:
    captured = llm_mock(
        lambda _request: httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
        )
    )

    result = await complete([{"role": "user", "content": "return json"}], json_mode=True)

    assert result == '{"ok": true}'
    assert captured["payload"]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (401, ErrorCode.LLM_AUTH),
        (402, ErrorCode.LLM_AUTH),
        (429, ErrorCode.LLM_RATE_LIMIT),
    ],
)
async def test_http_errors_are_mapped(llm_mock, status_code: int, expected_code: ErrorCode) -> None:
    llm_mock(lambda _request: httpx.Response(status_code, text="upstream"))

    with pytest.raises(AppError) as exc_info:
        await complete([{"role": "user", "content": "hello"}])

    assert exc_info.value.code is expected_code
    assert await get_costs() == []


async def test_timeout_is_mapped(llm_mock) -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=_request)

    llm_mock(timeout)

    with pytest.raises(AppError) as exc_info:
        await complete([{"role": "user", "content": "hello"}])

    assert exc_info.value.code is ErrorCode.LLM_TIMEOUT


async def test_missing_api_key_returns_not_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_settings(tmp_path, monkeypatch, api_key="")

    with pytest.raises(AppError) as exc_info:
        await complete([{"role": "user", "content": "hello"}])
    assert exc_info.value.code is ErrorCode.LLM_NOT_CONFIGURED

    with pytest.raises(AppError) as stream_exc_info:
        async for _chunk in stream([{"role": "user", "content": "hello"}]):
            pass
    assert stream_exc_info.value.code is ErrorCode.LLM_NOT_CONFIGURED


async def test_custom_pricing_is_used(llm_mock, tmp_path: Path) -> None:
    clear_custom_pricing()
    llm_mock(
        lambda _request: httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000},
            },
        )
    )
    from llmwiki.llm import pricing_for, save_custom_pricing, set_model_pricing

    set_model_pricing("custom-model", 1, 2)
    save_custom_pricing()
    assert pricing_for("custom-model") == ({"input": 1.0, "output": 2.0}, "custom")

    result = await complete([{"role": "user", "content": "hello"}], model="custom-model")

    assert result == "ok"
    records = await get_costs()
    assert records[0]["cost"] == 3.0
    assert records[0]["pricing_source"] == "custom"
    assert (tmp_path / ".llmwiki" / "model_pricing.json").exists()
    clear_custom_pricing()
