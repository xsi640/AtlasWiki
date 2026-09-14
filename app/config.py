"""配置与路径管理。

一切以文件为准：raw/ 是不可变原始素材，wiki/ 是 LLM 维护的知识库。
没有任何数据库 —— 整个知识库就是 data/kb/ 下的 Markdown 文件。
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CONFIG_PATH = ROOT / "config.yaml"
CONFIG_EXAMPLE_PATH = ROOT / "config.example.yaml"

# 知识库根目录（可通过 config.yaml 的 vault.path 覆盖）
DEFAULT_VAULT_DIR = DATA_DIR / "kb"

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

DEFAULTS: dict[str, Any] = {
    "server": {
        "host": "127.0.0.1",
        "port": 8765,
    },
    "vault": {
        "path": str(DEFAULT_VAULT_DIR),
    },
    "llm": {
        # 留空 api_key 时，系统用「确定性编译器」兜底，仍然会生成结构化 wiki
        "enabled": True,
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "max_tokens": 4096,
        "max_tool_rounds": 24,
        "extra_instructions": "",
    },
    "ingest": {
        # 收录后是否自动调用 LLM 编译进 wiki
        "auto_compile": True,
        # 单次编译最多让 LLM 读多少字符的原始素材
        "max_source_chars": 40000,
    },
    "fetch": {
        "timeout": 20,
        "user_agent": DEFAULT_UA,
        "bilibili_cookie": "",
        "proxy": "",
        "max_bytes": 8 * 1024 * 1024,
        "enable_ytdlp": True,
        "ytdlp_timeout": 60,
    },
    "lint": {
        "stale_days": 120,
    },
    "search": {
        "max_results": 40,
        "context_lines": 2,
    },
}

_cache: dict[str, Any] | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def ensure_dirs() -> None:
    for path in (DATA_DIR, UPLOAD_DIR, vault_dir()):
        path.mkdir(parents=True, exist_ok=True)
    for sub in ("raw", "raw/assets", "wiki", "wiki/sources", "wiki/entities", "wiki/concepts", "wiki/analyses"):
        (vault_dir() / sub).mkdir(parents=True, exist_ok=True)


def load_config(reload: bool = False) -> dict[str, Any]:
    global _cache
    if _cache is not None and not reload:
        return _cache
    raw: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            raw = {}
    cfg = _deep_merge(DEFAULTS, raw)
    _cache = cfg
    return cfg


def save_config(updates: dict[str, Any]) -> dict[str, Any]:
    current: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            current = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            current = {}
    merged = _deep_merge(current, updates)
    CONFIG_PATH.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return load_config(reload=True)


def llm_ready() -> bool:
    """是否走 LLM 编译。`enabled: false` 是硬开关 —— 即使填了 api_key 也强制用确定性编译器。"""
    cfg = load_config()["llm"]
    if not cfg.get("enabled", True):
        return False
    return bool(cfg.get("api_key"))


# --------------------------------------------------------------------------- #
# 便捷访问器（保证 config.yaml 里的每个键都真的有人读）
# --------------------------------------------------------------------------- #

def auto_compile() -> bool:
    """收录完成后是否自动编译进 wiki。"""
    return bool(load_config()["ingest"].get("auto_compile", True))


def max_source_chars() -> int:
    """单次编译最多让 LLM 读多少字符的原始素材。"""
    try:
        return max(2000, int(load_config()["ingest"].get("max_source_chars", 40000)))
    except Exception:
        return 40000


def search_limit() -> int:
    """检索默认返回条数。"""
    try:
        return max(1, int(load_config()["search"].get("max_results", 40)))
    except Exception:
        return 40


def ytdlp_timeout() -> int:
    """yt-dlp 单次调用超时（秒）。"""
    try:
        return max(10, int(load_config()["fetch"].get("ytdlp_timeout", 60)))
    except Exception:
        return 60


# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #

def vault_dir() -> Path:
    cfg = load_config()
    path = Path(str(cfg["vault"]["path"])).expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def raw_dir() -> Path:
    return vault_dir() / "raw"


def wiki_dir() -> Path:
    return vault_dir() / "wiki"


def write_default_config() -> None:
    if CONFIG_PATH.exists():
        return
    CONFIG_PATH.write_text(
        yaml.safe_dump(DEFAULTS, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def describe() -> dict[str, Any]:
    return {
        "vault": str(vault_dir()),
        "raw": str(raw_dir()),
        "wiki": str(wiki_dir()),
        "config": str(CONFIG_PATH),
        "llm_ready": llm_ready(),
    }
