"""素材生命周期服务（TASK-011）：列表、详情、编辑、软删除与恢复。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from atlaswiki.audit import AuditService
from atlaswiki.errors import AppError, ErrorCode
from atlaswiki.schema import MaterialKind, MaterialStatus
from atlaswiki.workspace.store import WikiStore

# TASK-003 底座中的类名为 WikiStore；这里保留需求中的语义别名。
MarkdownStore = WikiStore

_SOURCE_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_ACTIVE_JOB_STATUSES = {"queued", "running"}
_UPDATABLE_FIELDS = {"title", "tags", "note", "author", "published_at", "raw_meta"}


class SourceService:
    """封装 raw 素材文件的读取与生命周期写入。"""

    def __init__(
        self,
        *,
        store: MarkdownStore | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self._audit = audit or AuditService()
        self._write_lock = asyncio.Lock()

    async def list_sources(
        self,
        vault_path: Path | str,
        *,
        status: str | MaterialStatus | Sequence[str | MaterialStatus] | None = None,
        page: int = 1,
        size: int = 50,
    ) -> dict[str, Any]:
        """返回素材摘要、筛选后的 total 与四态计数。"""

        statuses = self._normalize_statuses(status)
        self._validate_pagination(page, size)
        store = WikiStore(vault_path, initialized=True)

        def _load() -> tuple[list[dict[str, Any]], dict[str, int]]:
            materials = [self._summary(store, path) for path in self._source_paths(store.vault)]
            materials.sort(key=lambda item: (str(item.get("updated_at") or ""), str(item["id"])))
            counts = {state.value: 0 for state in MaterialStatus}
            for item in materials:
                state = MaterialStatus(item["status"])
                counts[state.value] += 1
            if statuses is not None:
                allowed = {state.value for state in statuses}
                materials = [item for item in materials if item["status"] in allowed]
            return materials, counts

        materials, counts = await asyncio.to_thread(_load)
        start = (page - 1) * size
        return {
            "items": materials[start : start + size],
            "total": len(materials),
            "counts": counts,
        }

    async def get_source(self, vault_path: Path | str, source_id: str) -> dict[str, Any]:
        """按稳定 id 读取单个素材详情与派生页列表。"""

        store = WikiStore(vault_path, initialized=True)
        return await asyncio.to_thread(self._detail, store, source_id)

    async def update_source(
        self,
        vault_path: Path | str,
        source_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """部分更新素材；note 可改正文，外部素材只能改元数据。"""

        if not isinstance(updates, dict):
            raise AppError(ErrorCode.VALIDATION, "updates 必须是对象", {"updates": type(updates).__name__})

        async with self._write_lock:
            store = WikiStore(vault_path, initialized=True)
            current_path = await asyncio.to_thread(self._find_source_path, store, source_id)

            def _update() -> dict[str, Any]:
                document = store.read_markdown(current_path)
                material = self._material(document.metadata, current_path)
                self._ensure_not_busy(store.vault, source_id)
                kind = MaterialKind(material["kind"])

                if "content" in updates and kind is not MaterialKind.NOTE:
                    raise AppError(
                        ErrorCode.VALIDATION,
                        f"{kind.value} 素材正文不可编辑",
                        {"fields": {"content": "web/pdf 正文不可编辑"}},
                    )

                unknown = set(updates) - _UPDATABLE_FIELDS - {"content"}
                if kind is not MaterialKind.NOTE:
                    unknown |= set(updates) - {"title", "tags", "note"}
                if unknown:
                    raise AppError(
                        ErrorCode.VALIDATION,
                        f"{kind.value} 素材仅支持更新标题、标签和备注"
                        if kind is not MaterialKind.NOTE
                        else "包含不支持更新的字段",
                        {"fields": sorted(unknown)},
                    )

                metadata = dict(document.metadata)
                metadata.update(
                    {key: value for key, value in updates.items() if key != "content"},
                )
                metadata["status"] = MaterialStatus.STALE.value
                content = updates.get("content", document.content)
                store.write_markdown(current_path, metadata, content, update_timestamp=True)
                return self._detail(store, source_id) | {"needs_recompile": True}

            result = await asyncio.to_thread(_update)

        await self._record(
            vault_path,
            operation_type="source.update",
            source_id=source_id,
            affected_pages=[page["name"] for page in result.get("derived_pages", [])],
            affected_files=[current_path],
            reason="素材编辑",
        )
        return result

    async def delete_source(self, vault_path: Path | str, source_id: str) -> dict[str, Any]:
        """软删除素材，只改状态并返回当前派生页影响范围。"""

        async with self._write_lock:
            store = WikiStore(vault_path, initialized=True)
            source_path = await asyncio.to_thread(self._find_source_path, store, source_id)

            def _delete() -> tuple[dict[str, Any], list[dict[str, str]]]:
                document = store.read_markdown(source_path)
                self._material(document.metadata, source_path)
                self._ensure_not_busy(store.vault, source_id)
                derived_pages = self._derived_pages(store, source_id)
                metadata = dict(document.metadata)
                metadata["status"] = MaterialStatus.DELETED.value
                store.write_markdown(source_path, metadata, document.content, update_timestamp=True)
                return self._detail(store, source_id), derived_pages

            detail, derived_pages = await asyncio.to_thread(_delete)

        affected_pages = [page["name"] for page in derived_pages]
        await self._record(
            vault_path,
            operation_type="source.delete",
            source_id=source_id,
            affected_pages=affected_pages,
            affected_files=[source_path],
            reason="素材软删除",
        )
        return {
            "id": source_id,
            "status": detail["status"],
            "affected_page_count": len(derived_pages),
            "affected_pages": affected_pages,
        }

    async def restore_source(self, vault_path: Path | str, source_id: str) -> dict[str, Any]:
        """把已删除素材恢复为 normal。"""

        async with self._write_lock:
            store = WikiStore(vault_path, initialized=True)
            source_path = await asyncio.to_thread(self._find_source_path, store, source_id)

            def _restore() -> dict[str, Any]:
                document = store.read_markdown(source_path)
                material = self._material(document.metadata, source_path)
                if material["status"] is not MaterialStatus.DELETED:
                    raise AppError(
                        ErrorCode.VALIDATION,
                        "只有已删除素材可以恢复",
                        {"status": material["status"].value},
                    )
                metadata = dict(document.metadata)
                metadata["status"] = MaterialStatus.NORMAL.value
                store.write_markdown(source_path, metadata, document.content, update_timestamp=True)
                return self._detail(store, source_id)

            result = await asyncio.to_thread(_restore)

        await self._record(
            vault_path,
            operation_type="source.restore",
            source_id=source_id,
            affected_pages=[page["name"] for page in result.get("derived_pages", [])],
            affected_files=[source_path],
            reason="素材恢复",
        )
        return result

    @staticmethod
    def _normalize_statuses(
        status: str | MaterialStatus | Sequence[str | MaterialStatus] | None,
    ) -> list[MaterialStatus] | None:
        if status is None:
            return None
        raw_values = [status] if isinstance(status, (str, MaterialStatus)) else list(status)
        if not raw_values:
            return []
        try:
            return [MaterialStatus(value) for value in raw_values]
        except ValueError as exc:
            raise AppError(
                ErrorCode.VALIDATION,
                "status 筛选值非法",
                {"fields": {"status": "必须是 normal/failed/deleted/stale"}},
            ) from exc

    @staticmethod
    def _validate_pagination(page: int, size: int) -> None:
        fields: dict[str, str] = {}
        if page < 1:
            fields["page"] = "必须从 1 开始"
        if size < 1 or size > 200:
            fields["size"] = "必须在 1 到 200 之间"
        if fields:
            raise AppError(ErrorCode.VALIDATION, "分页参数非法", {"fields": fields})

    @staticmethod
    def _source_paths(vault: Path) -> list[Path]:
        raw_dir = vault / "raw"
        if not raw_dir.is_dir():
            return []
        return sorted(
            path.relative_to(vault)
            for path in raw_dir.rglob("*.md")
            if path.is_file() and not path.name.startswith(".")
        )

    @classmethod
    def _find_source_path(cls, store: WikiStore, source_id: str) -> Path:
        if not _SOURCE_ID_RE.fullmatch(source_id):
            raise AppError(
                ErrorCode.VALIDATION,
                "素材 id 必须是 12 位十六进制",
                {"source_id": source_id},
            )
        for path in cls._source_paths(store.vault):
            if path.stem == source_id:
                return path
            metadata = store.read_markdown(path).metadata
            if metadata.get("id") == source_id:
                return path
        raise AppError(ErrorCode.NOT_FOUND, "素材不存在", {"source_id": source_id})

    @classmethod
    def _material(cls, metadata: dict[str, Any], path: Path) -> dict[str, Any]:
        material_id = metadata.get("id", path.stem)
        if not isinstance(material_id, str) or not _SOURCE_ID_RE.fullmatch(material_id):
            raise AppError(
                ErrorCode.PARSE_FAILED,
                "素材 frontmatter id 非法",
                {"path": path.relative_to(path.parent.parent).as_posix(), "id": material_id},
            )
        try:
            kind = MaterialKind(metadata.get("kind"))
            status = MaterialStatus(metadata.get("status", MaterialStatus.NORMAL.value))
        except ValueError as exc:
            raise AppError(
                ErrorCode.PARSE_FAILED,
                "素材 frontmatter kind/status 非法",
                {"path": path.relative_to(path.parent.parent).as_posix()},
            ) from exc

        tags = metadata.get("tags", [])
        if not isinstance(tags, list):
            raise AppError(
                ErrorCode.PARSE_FAILED,
                "素材 tags 必须是列表",
                {"path": path.relative_to(path.parent.parent).as_posix()},
            )
        return {
            "id": material_id,
            "kind": kind,
            "status": status,
            "metadata": metadata,
            "tags": [str(tag) for tag in tags],
        }

    @classmethod
    def _summary(cls, store: WikiStore, path: Path) -> dict[str, Any]:
        document = store.read_markdown(path)
        material = cls._material(document.metadata, path)
        metadata = material["metadata"]
        return {
            "id": material["id"],
            "title": str(metadata.get("title", "")),
            "kind": material["kind"].value,
            "source_url": metadata.get("source_url"),
            "status": material["status"].value,
            "tags": material["tags"],
            "author": metadata.get("author"),
            "published_at": metadata.get("published_at"),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
            "derived_page_count": len(cls._derived_pages(store, material["id"])),
            "failure_reason": metadata.get("failure_reason"),
        }

    @classmethod
    def _detail(cls, store: WikiStore, source_id: str) -> dict[str, Any]:
        path = cls._find_source_path(store, source_id)
        document = store.read_markdown(path)
        material = cls._material(document.metadata, path)
        metadata = material["metadata"]
        busy = cls._is_busy(store.vault, source_id)
        return {
            "id": material["id"],
            "title": str(metadata.get("title", "")),
            "kind": material["kind"].value,
            "source_url": metadata.get("source_url"),
            "status": material["status"].value,
            "tags": material["tags"],
            "author": metadata.get("author"),
            "published_at": metadata.get("published_at"),
            "note": metadata.get("note"),
            "content": document.content,
            "content_editable": material["kind"] is MaterialKind.NOTE and not busy,
            "asset_path": metadata.get("asset_path"),
            "raw_meta": metadata.get("raw_meta", {}),
            "derived_pages": cls._derived_pages(store, source_id),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
            "failure_reason": metadata.get("failure_reason"),
        }

    @staticmethod
    def _derived_pages(store: WikiStore, source_id: str) -> list[dict[str, str]]:
        pages = []
        for page in store.read_pages():
            if page.metadata.get("origin_source") == source_id:
                pages.append(
                    {
                        "name": page.name,
                        "title": page.title,
                        "status": str(page.metadata.get("status", "")),
                    }
                )
        return pages

    @staticmethod
    def _ensure_not_busy(vault: Path, source_id: str) -> None:
        if SourceService._is_busy(vault, source_id):
            raise AppError(
                ErrorCode.SOURCE_BUSY,
                "素材正在编译中，暂时不可修改",
                {"source_id": source_id},
            )

    @staticmethod
    def _is_busy(vault: Path, source_id: str) -> bool:
        """读取 jobs.json；编译任务通过 kind/detail/source_id 与素材建立关联。"""

        jobs_file = vault / ".llmwiki" / "jobs.json"
        if not jobs_file.is_file():
            return False
        try:
            raw = json.loads(jobs_file.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw
        if not isinstance(jobs, list):
            return False
        for job in jobs:
            if not isinstance(job, dict) or job.get("status") not in _ACTIVE_JOB_STATUSES:
                continue
            if job.get("source_id") == source_id:
                return True
            marker = f"{job.get('kind', '')} {job.get('detail', '')}"
            if source_id in marker:
                return True
        return False

    async def _record(
        self,
        vault_path: Path | str,
        *,
        operation_type: str,
        source_id: str,
        affected_pages: Iterable[str],
        affected_files: Iterable[Path | str],
        reason: str,
    ) -> None:
        pages = sorted(set(affected_pages))
        files = [Path(vault_path) / item if not Path(item).is_absolute() else Path(item) for item in affected_files]
        await asyncio.to_thread(
            self._audit.record_task_completion,
            operation_type=operation_type,
            affected_pages=[source_id, *pages],
            affected_files=files,
            reason=reason,
            vault_path=vault_path,
        )


source_service = SourceService()
