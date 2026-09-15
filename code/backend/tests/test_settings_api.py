"""TASK-032 设置、成本与系统 API 验收测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from llmwiki.api.system import router as system_router
from llmwiki.config import Settings, config_store
from llmwiki.errors import AppError, ErrorCode


class FakeAsyncClient:
    """替换 httpx.AsyncClient，避免设置页连通性测试访问外部服务。"""

    fake_response: httpx.Response | None = None
    fake_exception: Exception | None = None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None

    async def post(self, *_args: Any, **_kwargs: Any) -> httpx.Response:
        if FakeAsyncClient.fake_exception is not None:
            raise FakeAsyncClient.fake_exception
        assert FakeAsyncClient.fake_response is not None
        return FakeAsyncClient.fake_response


def install_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """隔离全局配置缓存和配置文件。"""
    settings = Settings(
        vault_path=str(tmp_path / "vault"),
        llm={
            "provider": "openai-compatible",
            "base_url": "https://llm.example/v1",
            "model": "gpt-4o-mini",
            "api_key": "secret-key-1234",
            "timeout_s": 7,
            "max_cost_per_task_usd": 0.5,
        },
        git={"auto_commit": True, "auto_push": False, "remote_name": "origin"},
    )
    monkeypatch.setattr(config_store, "_cache", settings)
    monkeypatch.setattr(config_store, "_dir", tmp_path / "app-config")
    monkeypatch.setattr(config_store, "_path", tmp_path / "app-config" / "settings.json")
    return settings


def client() -> TestClient:
    """只装配被测 settings 路由和统一业务错误处理。"""
    app = FastAPI()

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    from llmwiki.api.settings import router

    app.include_router(router)
    app.include_router(system_router)
    return TestClient(app)


def write_git_config(vault: Path, remote_name: str = "origin") -> None:
    """创建足以验证远端解析的最小 git config。"""
    git_dir = vault / ".git"
    git_dir.mkdir(parents=True)
    git_dir.joinpath("config").write_text(
        "[core]\n\trepositoryformatversion = 0\n"
        f'[remote "{remote_name}"]\n\turl = https://example.com/repo.git\n',
        encoding="utf-8",
    )


def test_get_settings_masks_api_key_and_detects_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_settings(tmp_path, monkeypatch)
    write_git_config(Path(config_store.load().vault_path))

    with client() as test_client:
        response = test_client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["vault_path"] == str(tmp_path / "vault")
    assert payload["llm"]["has_key"] is True
    assert payload["llm"]["key_hint"] == "1234"
    assert "secret-key-1234" not in json.dumps(payload)
    assert payload["git"]["has_remote"] is True


def test_update_settings_round_trip_keeps_empty_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = install_settings(tmp_path, monkeypatch)

    with client() as test_client:
        response = test_client.put(
            "/api/settings",
            json={
                "vault_path": str(tmp_path / "next-vault"),
                "llm_provider": "custom",
                "llm_base_url": "https://another.example/v1/",
                "llm_model": "gpt-4.1-mini",
                "llm_api_key": "",
                "llm_timeout_s": 31,
                "llm_max_cost_per_task_usd": 2.5,
                "git_auto_commit": False,
                "git_auto_push": True,
                "git_remote_name": "upstream",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["vault_path"] == str(tmp_path / "next-vault")
    assert payload["llm"] == {
        "provider": "custom",
        "base_url": "https://another.example/v1/",
        "model": "gpt-4.1-mini",
        "has_key": True,
        "key_hint": "1234",
        "timeout_s": 31,
        "max_cost_per_task_usd": 2.5,
    }
    assert payload["git"]["auto_commit"] is False
    assert payload["git"]["auto_push"] is True
    assert payload["git"]["remote_name"] == "upstream"

    persisted = json.loads(config_store.path.read_text(encoding="utf-8"))
    assert persisted["llm"]["api_key"] == "secret-key-1234"
    assert settings.llm.base_url == "https://another.example/v1/"


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(200, "ok"), (401, "auth_failed"), (429, "rate_limited")],
)
def test_connection_maps_http_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected: str,
) -> None:
    install_settings(tmp_path, monkeypatch)
    FakeAsyncClient.fake_exception = None
    FakeAsyncClient.fake_response = httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://llm.example/v1/chat/completions"),
    )
    monkeypatch.setattr("llmwiki.api.settings.httpx.AsyncClient", FakeAsyncClient)

    with client() as test_client:
        response = test_client.post("/api/settings/test-connection")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is (expected == "ok")
    assert payload["status"] == expected


def test_connection_distinguishes_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_settings(tmp_path, monkeypatch)
    FakeAsyncClient.fake_response = None
    FakeAsyncClient.fake_exception = httpx.TimeoutException("timed out")
    monkeypatch.setattr("llmwiki.api.settings.httpx.AsyncClient", FakeAsyncClient)

    with client() as test_client:
        response = test_client.post("/api/settings/test-connection")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "timeout"
    assert payload["timeout_s"] == 7


def test_connection_requires_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = install_settings(tmp_path, monkeypatch)
    settings.llm.api_key = ""

    with client() as test_client:
        response = test_client.post("/api/settings/test-connection")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == ErrorCode.LLM_NOT_CONFIGURED.value


def test_git_sync_uses_audit_operations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = install_settings(tmp_path, monkeypatch)
    calls: list[tuple[str, str]] = []

    class FakeGitOperations:
        def sync(self, *, vault_path: str, remote_name: str) -> object:
            calls.append((vault_path, remote_name))
            return type("Result", (), {"stdout": "pushed\n", "stderr": ""})()

    monkeypatch.setattr("llmwiki.audit.GitOperations", FakeGitOperations)
    with client() as test_client:
        response = test_client.post("/api/settings/git/sync")

    assert response.status_code == 200
    assert calls == [(settings.vault_path, settings.git.remote_name)]
    assert response.json() == {"ok": True, "stdout": "pushed\n", "stderr": ""}


def test_git_sync_without_remote_returns_git_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_settings(tmp_path, monkeypatch)
    Path(config_store.load().vault_path).mkdir(parents=True)

    with client() as test_client:
        response = test_client.post("/api/settings/git/sync")

    assert response.status_code == 502
    payload = response.json()
    assert payload["error"]["code"] == ErrorCode.GIT_FAILED.value
    assert payload["error"]["details"]["stderr"]


def test_open_data_folder_launches_system_file_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API-003 必须把打开动作交给系统文件管理器，而不是只返回路径。"""
    install_settings(tmp_path, monkeypatch)
    vault = Path(config_store.load().vault_path)
    vault.mkdir(parents=True)
    commands: list[list[str]] = []

    def fake_popen(command: list[str], *_args: Any, **_kwargs: Any) -> object:
        commands.append(command)
        return object()

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("llmwiki.api.system.subprocess.Popen", fake_popen)

    with client() as test_client:
        response = test_client.post("/api/system/open-folder")

    assert response.status_code == 200
    assert response.json() == {"opened": True, "path": str(vault)}
    assert commands == [["open", str(vault)]]


def write_cost_file(vault: Path, records: list[dict[str, Any]]) -> None:
    metadata = vault / ".llmwiki"
    metadata.mkdir(parents=True)
    metadata.joinpath("costs.json").write_text(json.dumps(records), encoding="utf-8")


def test_costs_aggregates_day_operation_and_pricing_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_settings(tmp_path, monkeypatch)
    write_cost_file(
        Path(config_store.load().vault_path),
        [
            {
                "at": "2026-09-14T10:00:00+08:00",
                "operation": "compile",
                "model": "gpt-4o-mini",
                "input_tokens": 100,
                "output_tokens": 200,
                "cost": 0.001,
                "pricing_source": "builtin",
                "job_id": "job-1",
            },
            {
                "at": "2026-09-15T11:00:00+08:00",
                "operation": "ask",
                "model": "custom-model",
                "input_tokens": 10,
                "output_tokens": 20,
                "cost": 0.002,
                "pricing_source": "custom",
            },
            {
                "at": "2026-09-15T12:00:00+08:00",
                "operation": "compile",
                "model": "gpt-4o",
                "input_tokens": 1,
                "output_tokens": 2,
                "cost": 0.0001,
                "pricing_source": "builtin",
            },
        ],
    )

    with client() as test_client:
        response = test_client.get("/api/settings/costs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_usd"] == pytest.approx(0.0031)
    assert payload["currency"] == "USD"
    assert payload["pricing_source"] == "custom"
    assert len(payload["entries"]) == 3
    assert payload["entries"][0] == {
        "model": "gpt-4o-mini",
        "input_tokens": 100,
        "output_tokens": 200,
        "cost_usd": 0.001,
        "source": "compile",
        "created_at": "2026-09-14T10:00:00+08:00",
        "pricing_source": "builtin",
        "job_id": "job-1",
    }
    assert payload["by_day"] == [
        {"date": "2026-09-14", "cost": 0.001, "calls": 1},
        {"date": "2026-09-15", "cost": 0.0021, "calls": 2},
    ]
    assert payload["by_operation"] == [
        {"operation": "ask", "cost": 0.002, "calls": 1},
        {"operation": "compile", "cost": 0.0011, "calls": 2},
    ]


def test_costs_report_builtin_without_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_settings(tmp_path, monkeypatch)

    with client() as test_client:
        response = test_client.get("/api/settings/costs")

    assert response.status_code == 200
    assert response.json() == {
        "entries": [],
        "total_usd": 0,
        "currency": "USD",
        "pricing_source": "builtin",
        "by_day": [],
        "by_operation": [],
    }


def test_costs_pricing_source_reflects_custom_file_without_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_settings(tmp_path, monkeypatch)
    metadata = Path(config_store.load().vault_path) / ".llmwiki"
    metadata.mkdir(parents=True)
    metadata.joinpath("model_pricing.json").write_text(
        json.dumps({"custom-model": {"input": 1.0, "output": 2.0}}),
        encoding="utf-8",
    )

    with client() as test_client:
        response = test_client.get("/api/settings/costs")

    assert response.status_code == 200
    assert response.json()["pricing_source"] == "custom"
