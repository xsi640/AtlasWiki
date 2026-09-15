"""设置读写（含密钥文件），ADR-010：key 存仓库外。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field


def _app_config_dir() -> Path:
    """返回应用配置目录，跨平台。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(base) / "llmwiki"


class LlmSettings(BaseModel):
    """LLM 连接配置。"""

    provider: str = "openai-compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    timeout_s: int = 120
    max_cost_per_task_usd: float = 1.0


class GitSettings(BaseModel):
    """git 同步配置（ADR-009）。"""

    auto_commit: bool = True
    auto_push: bool = False
    remote_name: str = "origin"
    ssh_key_path: str = ""


class Settings(BaseModel):
    """顶层设置，序列化到密钥文件。"""

    vault_path: str = Field(default="", alias="vault_path")
    llm: LlmSettings = Field(default_factory=LlmSettings)
    git: GitSettings = Field(default_factory=GitSettings)

    model_config = {"populate_by_name": True}


class ConfigStore:
    """读取 / 写入密钥文件，进程内缓存。"""

    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or _app_config_dir()
        self._path = self._dir / "settings.json"
        self._cache: Settings | None = None

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Settings:
        if self._cache is not None:
            return self._cache
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text("utf-8"))
                self._cache = Settings.model_validate(data)
            except Exception:
                self._cache = Settings()
        else:
            self._cache = Settings()
        return self._cache

    def save(self, settings: Settings) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(settings.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
        self._cache = settings

    @property
    def llm_configured(self) -> bool:
        return bool(self.load().llm.api_key)


# 模块级单例，供 API 与服务层共享。
config_store = ConfigStore()
