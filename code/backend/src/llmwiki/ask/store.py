"""问答记录持久化：`.llmwiki/queries.json` 追加式列表。"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    """返回 ISO8601 UTC 时间。"""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def make_query_id(existing: list[dict[str, Any]] | None = None) -> str:
    """生成人类可读 ID；同一秒内自动追加短随机后缀。"""

    used = {str(item.get("id")) for item in existing or []}
    base = datetime.now(UTC).strftime("q-%Y%m%d-%H%M")
    if base not in used:
        return base
    while True:
        candidate = f"{base}-{uuid.uuid4().hex[:6]}"
        if candidate not in used:
            return candidate


class QueryStore:
    """进程内加锁、全量原子写入的问答历史仓库。"""

    def __init__(self, vault_path: str | Path) -> None:
        self.vault_path = Path(vault_path).expanduser().resolve()
        self._lock = asyncio.Lock()

    @property
    def path(self) -> Path:
        return self.vault_path / ".llmwiki" / "queries.json"

    def _read_sync(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("queries.json 损坏") from exc
        if not isinstance(value, list):
            raise ValueError("queries.json 必须是 JSON 数组")
        return [item for item in value if isinstance(item, dict)]

    def _write_sync(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        temporary = Path(raw_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(records, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    async def list_all(self) -> list[dict[str, Any]]:
        """按时间正序返回全部记录。"""

        async with self._lock:
            return await asyncio.to_thread(self._read_sync)

    async def append(self, record: dict[str, Any]) -> dict[str, Any]:
        """追加一条问答记录并返回带 ID 的记录。"""

        async with self._lock:
            records = await asyncio.to_thread(self._read_sync)
            output = dict(record)
            if not output.get("id"):
                output["id"] = make_query_id(records)
            output.setdefault("created_at", utc_now())
            output.setdefault("saved_page", None)
            records.append(output)
            await asyncio.to_thread(self._write_sync, records)
            return output

    async def get(self, query_id: str) -> dict[str, Any] | None:
        """读取一条历史记录。"""

        records = await self.list_all()
        return next((item for item in reversed(records) if item.get("id") == query_id), None)

    async def update(self, query_id: str, updater) -> dict[str, Any]:
        """更新一条记录；updater 接收副本并返回更新后的字典。"""

        async with self._lock:
            records = await asyncio.to_thread(self._read_sync)
            for index, item in enumerate(records):
                if item.get("id") != query_id:
                    continue
                updated = updater(dict(item))
                updated["id"] = query_id
                records[index] = updated
                await asyncio.to_thread(self._write_sync, records)
                return updated
        raise KeyError(query_id)

    async def delete(self, query_id: str) -> bool:
        """删除一条历史记录，返回是否确实删除。"""

        async with self._lock:
            records = await asyncio.to_thread(self._read_sync)
            remaining = [item for item in records if item.get("id") != query_id]
            if len(remaining) == len(records):
                return False
            await asyncio.to_thread(self._write_sync, remaining)
            return True
