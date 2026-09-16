"""LLM 用量与成本记账。

价格单位统一为 USD / 1,000,000 tokens；账本文件为 vault 下的
``.llmwiki/costs.json``，写入采用“读-追加-原子替换”。
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from llmwiki.config import config_store

# 与产品文档一致：USD / 百万 token。
DEFAULT_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "claude-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "deepseek-chat": {"input": 0.27, "output": 1.10},
}

_cost_lock = asyncio.Lock()
_custom_pricing: dict[str, dict[str, float]] = {}


def _vault_root() -> Path:
    """返回成本文件的 vault 根目录；空配置时退回当前后端工作目录。"""
    vault_path = config_store.load().vault_path
    return Path(vault_path).expanduser() if vault_path else Path.cwd()


def _costs_path() -> Path:
    return _vault_root() / ".llmwiki" / "costs.json"


def _custom_pricing_path() -> Path:
    return _vault_root() / ".llmwiki" / "model_pricing.json"


def set_model_pricing(model: str, input_usd_per_million: float, output_usd_per_million: float) -> None:
    """设置进程内自定义单价；调用方随后可调用 ``save_custom_pricing`` 持久化。"""
    if not model.strip():
        raise ValueError("model 不能为空")
    if input_usd_per_million < 0 or output_usd_per_million < 0:
        raise ValueError("模型单价不能为负数")
    _custom_pricing[model.strip()] = {
        "input": float(input_usd_per_million),
        "output": float(output_usd_per_million),
    }


def clear_custom_pricing() -> None:
    """清空进程内自定义单价，主要用于测试和设置重置。"""
    _custom_pricing.clear()


def save_custom_pricing() -> None:
    """把当前自定义单价持久化到 vault 元数据目录。"""
    path = _custom_pricing_path()
    _atomic_json_write(path, _custom_pricing)


def _load_file_pricing() -> dict[str, dict[str, float]]:
    path = _custom_pricing_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}

    pricing: dict[str, dict[str, float]] = {}
    for model, value in raw.items():
        if not isinstance(model, str) or not isinstance(value, dict):
            continue
        try:
            input_price = float(value["input"])
            output_price = float(value["output"])
        except (KeyError, TypeError, ValueError):
            continue
        if input_price >= 0 and output_price >= 0:
            pricing[model] = {"input": input_price, "output": output_price}
    return pricing


def pricing_for(model: str) -> tuple[dict[str, float], str]:
    """返回指定模型单价与其来源（``custom`` / ``builtin``）。"""
    normalized = model.strip()
    pricing = _custom_pricing.get(normalized)
    if pricing is not None:
        return dict(pricing), "custom"

    file_pricing = _load_file_pricing().get(normalized)
    if file_pricing is not None:
        return dict(file_pricing), "custom"
    return dict(DEFAULT_MODEL_PRICING.get(normalized, {"input": 0.0, "output": 0.0})), "builtin"


def estimate_tokens(text: str) -> int:
    """对无 usage 响应做保守 token 估算，确保流式调用也能记账。"""
    return max(1, (len(text) + 3) // 4)


def messages_text(messages: list[dict[str, Any]]) -> str:
    """将 Chat Completions 消息序列化为 token 估算用的文本。"""
    chunks: list[str] = []
    for message in messages:
        role = str(message.get("role", ""))
        content = message.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, sort_keys=True)
        chunks.append(f"{role}\n{content}")
    return "\n".join(chunks)


def usage_from_response(response_json: dict[str, Any], messages: list[dict[str, Any]], output: str) -> tuple[int, int]:
    """优先读取 OpenAI usage，缺失时回退到字符估算。"""
    usage = response_json.get("usage")
    if isinstance(usage, dict):
        try:
            input_tokens = int(usage.get("prompt_tokens", 0))
            output_tokens = int(usage.get("completion_tokens", 0))
        except (TypeError, ValueError):
            input_tokens = output_tokens = 0
        if input_tokens >= 0 and output_tokens >= 0:
            return input_tokens, output_tokens
    return estimate_tokens(messages_text(messages)), estimate_tokens(output)


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> tuple[float, dict[str, float], str]:
    """按百万 token 单价计算费用，返回金额、单价和定价来源。"""
    pricing, source = pricing_for(model)
    cost = input_tokens * pricing["input"] / 1_000_000
    cost += output_tokens * pricing["output"] / 1_000_000
    return cost, pricing, source


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("costs.json 必须是 JSON 数组")
    return [record for record in value if isinstance(record, dict)]


def _atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _append_record_sync(record: dict[str, Any]) -> None:
    path = _costs_path()
    records = _read_records(path)
    records.append(record)
    _atomic_json_write(path, records)


async def record_usage(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    operation: str = "llm",
    job_id: str | None = None,
) -> dict[str, Any]:
    """追加一条成本流水并返回该记录。"""
    cost, pricing, pricing_source = calculate_cost(model, input_tokens, output_tokens)
    record: dict[str, Any] = {
        "at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "operation": operation,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": input_tokens * pricing["input"] / 1_000_000,
        "output_cost": output_tokens * pricing["output"] / 1_000_000,
        "cost": round(cost, 8),
        "currency": "USD",
        "pricing_source": pricing_source,
    }
    if job_id is not None:
        record["job_id"] = job_id

    async with _cost_lock:
        await asyncio.to_thread(_append_record_sync, record)
    return record


async def get_costs() -> list[dict[str, Any]]:
    """返回全部成本流水；调用方可自行按日、操作或模型聚合。"""
    async with _cost_lock:
        return await asyncio.to_thread(_read_records, _costs_path())


def read_job_cost(vault_path: str | Path, job_id: str) -> float:
    """从指定 vault 的成本账本汇总单个任务的累计花费（只读，不经过全局配置）。"""

    path = Path(vault_path).expanduser() / ".llmwiki" / "costs.json"
    if not path.is_file():
        return 0.0
    try:
        records = _read_records(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return 0.0
    return round(
        sum(float(record.get("cost", 0)) for record in records if record.get("job_id") == job_id),
        8,
    )


async def get_cost_summary() -> dict[str, Any]:
    """提供成本看板所需的完整聚合结构。"""
    records = await get_costs()
    total = round(sum(float(record.get("cost", 0)) for record in records), 8)

    by_day: dict[str, dict[str, Any]] = {}
    by_operation: dict[str, dict[str, Any]] = {}
    for record in records:
        day = str(record.get("at", ""))[:10]
        operation = str(record.get("operation", "llm"))
        cost = float(record.get("cost", 0))
        for bucket, key in ((by_day, day), (by_operation, operation)):
            item = bucket.setdefault(key, {"cost": 0.0, "calls": 0})
            item["cost"] = round(item["cost"] + cost, 8)
            item["calls"] += 1

    pricing_source = "builtin"
    if _custom_pricing or _load_file_pricing():
        pricing_source = "custom"
    return {
        "currency": "USD",
        "range": "all",
        "total": total,
        "by_day": [
            {"date": day, "cost": value["cost"], "calls": value["calls"]}
            for day, value in sorted(by_day.items())
        ],
        "by_operation": [
            {"operation": operation, "cost": value["cost"], "calls": value["calls"]}
            for operation, value in sorted(by_operation.items())
        ],
        "recent": records[-20:],
        "pricing_source": pricing_source,
    }
