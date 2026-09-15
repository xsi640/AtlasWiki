"""编译引擎核心编排（TASK-013）。"""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from llmwiki.audit import AuditService
from llmwiki.compile.prompts import build_compile_messages
from llmwiki.config import ConfigStore
from llmwiki.errors import AppError, ErrorCode
from llmwiki.jobs import Job, JobQueue, job_queue
from llmwiki.llm import complete as default_llm_complete
from llmwiki.schema import MaterialStatus, PageType, normalize_page_name
from llmwiki.workspace.links import extract_links
from llmwiki.workspace.store import RESERVED_PAGE_NAMES, PageDraft, atomic_write_bytes
from llmwiki.workspace.store import WikiStore as MarkdownStore


class LlmCompleter(Protocol):
    """编译引擎需要的最小 LLM 接口。"""

    async def complete(self, messages: list[dict[str, str]], *, json_mode: bool) -> str:
        """返回助手文本。"""
        raise NotImplementedError


class AuditCompleter(Protocol):
    """编译引擎需要的最小审计接口。"""

    def record_task_completion(self, **payload: Any) -> Any:
        """记录任务完成审计。"""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class CompiledSource:
    """从 raw/ 素材文件读取出的编译输入。"""

    source_id: str
    title: str
    content: str
    relative_path: Path
    kind: str
    status: str


@dataclass(frozen=True, slots=True)
class CompiledPage:
    """一次编译中准备落盘的页面。"""

    name: str
    title: str
    page_type: PageType
    zone: str
    content: str
    created: bool


@dataclass(frozen=True, slots=True)
class CompileChange:
    """页面级变更记录。"""

    name: str
    title: str
    page_type: PageType
    action: str
    path: Path


@dataclass(slots=True)
class _CompileManifest:
    """供后续变更清单 API 使用的任务内状态。"""

    job_id: str
    items: list[CompileChange] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为 JSON 可序列化对象。"""

        return {
            "job_id": self.job_id,
            "items": [
                {**asdict(item), "path": item.path.as_posix(), "page_type": item.page_type.value}
                for item in self.items
            ],
            "failed_sources": self.failed_sources,
        }


class CompileEngine:
    """读素材、调用 LLM、校验结构、原子写页面，并串行提交到写入队列。"""

    def __init__(
        self,
        *,
        llm: LlmCompleter | Any | None = None,
        audit_service: AuditCompleter | AuditService | None = None,
        queue: JobQueue = job_queue,
        config_store_override: ConfigStore | None = None,
    ) -> None:
        """依赖均可注入；生产路径默认使用冻结契约中的全局单例。"""

        self._llm = llm
        self._audit = audit_service or AuditService()
        self._queue = queue
        self._config = config_store_override

    @property
    def config_store(self) -> ConfigStore:
        """返回当前配置仓库。"""

        from llmwiki.config import config_store as default_config_store

        return self._config or default_config_store

    async def start_compile(self, vault_path: str | Path, source_ids: list[str]) -> Job:
        """校验入口参数后，把编译任务提交到全局串行写入队列。"""

        normalized_ids = self._validate_source_ids(source_ids)
        # 尽早初始化骨架；队列持久化文件也依赖 .llmwiki 目录。
        await asyncio.to_thread(self._make_store, vault_path)
        return await self._queue.submit(
            "compile",
            lambda job: self.compile_sources(job, vault_path, normalized_ids),
            total=len(normalized_ids),
        )

    async def compile_sources(
        self,
        job: Job,
        vault_path: str | Path,
        source_ids: list[str],
    ) -> None:
        """在写入队列 worker 中顺序编译多个素材。"""

        normalized_ids = self._validate_source_ids(source_ids)
        store = await asyncio.to_thread(self._make_store, vault_path)
        manifest = _CompileManifest(job_id=job.id)

        for source_id in normalized_ids:
            source = await asyncio.to_thread(self._read_source, store, source_id)
            await self._publish_step(job, source, "读取素材原文")
            changes = await self._compile_one(job, store, source)
            manifest.items.extend(changes)
            await self._update_progress(
                job,
                done=min(job.done + 1, job.total),
                detail=f"{source.title} · 编译完成",
            )

        await asyncio.to_thread(self._write_manifest, store, manifest)
        await self._record_audit(store, manifest)
        await self._update_progress(job, detail=f"编译完成：{len(manifest.items)} 个页面变更")

    @staticmethod
    def _validate_source_ids(source_ids: list[str]) -> list[str]:
        """确保至少有一个不重复的素材 ID。"""

        if not isinstance(source_ids, list) or not source_ids:
            raise AppError(ErrorCode.VALIDATION, "source_ids 不能为空")
        normalized = [str(source_id).strip() for source_id in source_ids]
        if any(not source_id for source_id in normalized):
            raise AppError(ErrorCode.VALIDATION, "source_id 不能为空")
        if len(set(normalized)) != len(normalized):
            raise AppError(ErrorCode.VALIDATION, "source_ids 存在重复项")
        return normalized

    def _make_store(self, vault_path: str | Path) -> MarkdownStore:
        """创建并补齐 vault 骨架。"""

        return MarkdownStore(Path(vault_path).expanduser().resolve(), initialized=True)

    def _read_source(self, store: MarkdownStore, source_id: str) -> CompiledSource:
        """按 frontmatter id 定位 raw/ 下的一素材一文件。"""

        candidates: list[tuple[Path, Any, str]] = []
        raw_dir = store.vault / "raw"
        if raw_dir.is_dir():
            for path in raw_dir.glob("*.md"):
                document = store.read_markdown(path.relative_to(store.vault))
                candidate_id = str(document.metadata.get("id", "")).strip()
                if candidate_id == source_id:
                    candidates.append((path.relative_to(store.vault), document, candidate_id))

        if not candidates:
            raise AppError(ErrorCode.NOT_FOUND, "素材不存在", {"source_id": source_id})
        if len(candidates) > 1:
            raise AppError(
                ErrorCode.VALIDATION,
                "素材 ID 重复",
                {"source_id": source_id, "count": len(candidates)},
            )

        relative_path, document, _ = candidates[0]
        status = str(document.metadata.get("status", MaterialStatus.NORMAL.value))
        if status == MaterialStatus.DELETED.value:
            raise AppError(ErrorCode.NOT_FOUND, "素材已删除", {"source_id": source_id})
        content = document.content.strip()
        if not content:
            raise AppError(ErrorCode.VALIDATION, "素材正文为空", {"source_id": source_id})
        return CompiledSource(
            source_id=source_id,
            title=str(document.metadata.get("title") or source_id),
            content=content,
            relative_path=relative_path,
            kind=str(document.metadata.get("kind", "note")),
            status=status,
        )

    async def _compile_one(self, job: Job, store: MarkdownStore, source: CompiledSource) -> list[CompileChange]:
        """执行一个素材的读取 → LLM → 校验 → 原子写 → 索引流程。"""

        await self._publish_step(job, source, "调用 LLM 生成结构化结果")
        messages = await asyncio.to_thread(self._build_messages, store, source)
        raw_output = await self._call_llm(messages)
        payload = _parse_llm_payload(raw_output)
        # 校验、命名冲突处理和互链补全都发生在第一次磁盘写入之前。
        pages = await asyncio.to_thread(self._plan_pages, store, source, payload)
        await self._publish_step(job, source, "写入并互链 wiki 页面")

        changes: list[CompileChange] = []
        for page in pages:
            written = await asyncio.to_thread(self._write_page, store, source, page)
            changes.append(
                CompileChange(
                    name=written.name,
                    title=written.title,
                    page_type=page.page_type,
                    action="created" if page.created else "updated",
                    path=written.relative_path,
                )
            )

        await asyncio.to_thread(self._update_index_and_links, store)
        await self._publish_step(job, source, "更新索引完成")
        return changes

    def _build_messages(self, store: MarkdownStore, source: CompiledSource) -> list[dict[str, str]]:
        """构造请求，不读取页面正文，避免大库请求失控。"""

        return build_compile_messages(
            source_title=source.title,
            source_content=source.content,
            existing_pages=store.list_page_names(),
        )

    async def _call_llm(self, messages: list[dict[str, str]]) -> str:
        """调用注入的 mock/客户端，或在生产路径走冻结的 complete 契约。"""

        if self._llm is not None:
            completer = getattr(self._llm, "complete", None)
            if completer is not None:
                result = completer(messages, json_mode=True)
            elif callable(self._llm):
                result = self._llm(messages, json_mode=True)
            else:
                raise AppError(ErrorCode.VALIDATION, "LLM 注入对象不可调用")
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, str):
                raise AppError(ErrorCode.VALIDATION, "LLM 调用必须返回文本")
            return result

        settings = self.config_store.load().llm
        if not settings.api_key.strip():
            raise AppError(
                ErrorCode.LLM_NOT_CONFIGURED,
                "LLM API key 未配置",
                {"base_url": settings.base_url},
            )
        return await default_llm_complete(messages, json_mode=True, operation="compile", job_id=None)

    def _plan_pages(
        self,
        store: MarkdownStore,
        source: CompiledSource,
        payload: dict[str, Any],
    ) -> list[CompiledPage]:
        """校验 JSON 结构、处理同名冲突，并生成带互链的页面草案。"""

        existing = {page.name: page for page in store.read_pages()}
        used_names = set(existing)
        summary_name, summary_title, summary_zone, summary_content = _validate_summary(payload)

        # 同一 source 先前产出的页面允许更新；其他来源的同名页一律改名保护。
        summary_name = self._resolve_name(
            store,
            existing,
            used_names,
            desired=summary_name,
            title=summary_title,
            page_type=PageType.SOURCE,
            source_id=source.source_id,
        )
        used_names.add(summary_name)

        pages = [
            CompiledPage(
                name=summary_name,
                title=summary_title,
                page_type=PageType.SOURCE,
                zone=summary_zone,
                content=summary_content,
                created=summary_name not in existing,
            )
        ]
        child_names: list[str] = []

        for spec, page_type in (
            (_child_list(payload, "concept_pages"), PageType.CONCEPT),
            (_child_list(payload, "entity_pages"), PageType.ENTITY),
        ):
            for item in spec:
                normalized, title = _validate_child(item, page_type)
                name = self._resolve_name(
                    store,
                    existing,
                    used_names,
                    desired=normalized,
                    title=title,
                    page_type=page_type,
                    source_id=source.source_id,
                )
                used_names.add(name)
                child_names.append(name)
                pages.append(
                    CompiledPage(
                        name=name,
                        title=title,
                        page_type=page_type,
                        zone=str(item.get("zone") or summary_zone),
                        content=_with_links(
                            str(item["content"]).strip(),
                            declared_links=item.get("links", []),
                            required_links=[summary_name],
                        ),
                        created=name not in existing,
                    )
                )

        summary_content = _with_links(summary_content, declared_links=[], required_links=child_names)
        contradictions = payload.get("contradictions", [])
        if contradictions:
            summary_content = _append_contradictions(summary_content, contradictions)
        pages[0] = CompiledPage(
            name=summary_name,
            title=summary_title,
            page_type=PageType.SOURCE,
            zone=summary_zone,
            content=summary_content,
            created=summary_name not in existing,
        )
        return pages

    def _resolve_name(
        self,
        store: MarkdownStore,
        existing: dict[str, Any],
        used_names: set[str],
        *,
        desired: str,
        title: str,
        page_type: PageType,
        source_id: str,
    ) -> str:
        """同一来源可更新；来源不同或人工编辑过的页面永远不覆盖。"""

        if desired in existing:
            page = existing[desired]
            same_origin = (
                page.metadata.get("origin_source") == source_id
                and page.page_type is page_type
                and not bool(page.metadata.get("human_edited", False))
            )
            if same_origin:
                return desired
        return self._unique_name(store, used_names, desired or normalize_page_name(title), page_type)

    @staticmethod
    def _unique_name(
        store: MarkdownStore,
        used_names: set[str],
        desired: str,
        page_type: PageType,
    ) -> str:
        """为冲突页名追加 -2、-3；函数式命名便于测试和后续扩展。"""

        base = normalize_page_name(desired)
        candidate = base
        serial = 2
        while True:
            # page_path 会再次校验空名和系统保留名。
            store.page_path(candidate, page_type)
            if candidate not in used_names and candidate not in RESERVED_PAGE_NAMES:
                return candidate
            candidate = f"{base}-{serial}"
            serial += 1

    @staticmethod
    def _write_page(
        store: MarkdownStore,
        source: CompiledSource,
        page: CompiledPage,
    ) -> Any:
        """原子写入一个页面，links 由存储层从正文重新解析。"""

        return store.write_page(
            PageDraft(
                name=page.name,
                title=page.title,
                page_type=page.page_type,
                source_type="compiled",
                zone=page.zone,
                content=page.content,
                status="active",
                origin_source=source.source_id,
            )
        )

    @staticmethod
    def _update_index_and_links(store: MarkdownStore) -> None:
        """重建轻量索引并强制构建双向链接索引。"""

        pages = store.read_pages()
        lines = ["# 页面索引", "", "| 页面 | 类型 | 分区 | 摘要 |", "| --- | --- | --- | --- |"]
        for page in pages:
            first_line = next(
                (line.strip().lstrip("# ").strip() for line in page.content.splitlines() if line.strip()),
                "",
            )
            lines.append(
                f"| [[{page.name}]] | {page.page_type.value} "
                f"| {page.metadata.get('zone', '')} | {first_line.replace('|', '\\|')} |"
            )
        store.write_markdown(
            "wiki/index.md",
            {
                "title": "页面索引",
                "type": "analysis",
                "source_type": "compiled",
                "zone": "系统",
                "human_edited": False,
                "status": "active",
            },
            "\n".join(lines) + "\n",
            update_timestamp=True,
        )
        link_index = store.link_index()
        if not link_index.nodes:
            raise AppError(ErrorCode.VALIDATION, "索引重建后没有 wiki 页面")

    @staticmethod
    def _write_manifest(store: MarkdownStore, manifest: _CompileManifest) -> None:
        """把本次页面变更写到运行时目录，供 API 层读取。"""

        path = store.vault / ".llmwiki" / "compile" / f"{manifest.job_id}.json"
        atomic_write_bytes(path, json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2).encode("utf-8"))

    async def _record_audit(self, store: MarkdownStore, manifest: _CompileManifest) -> None:
        """记录审计日志并自动 git commit。"""

        result = self._audit.record_task_completion(
            operation_type="compile",
            affected_pages=[item.name for item in manifest.items],
            affected_files=[*[item.path for item in manifest.items], store.vault / "wiki" / "index.md"],
            reason=f"编译任务 {manifest.job_id}",
            vault_path=store.vault,
        )
        if inspect.isawaitable(result):
            await result

    async def _update_progress(
        self,
        job: Job,
        *,
        detail: str,
        done: int | None = None,
    ) -> None:
        """队列内走标准进度接口；独立调用 compile_sources 时也能更新 Job。"""

        if self._queue.get(job.id) is job:
            await self._queue.update_progress(job, done=done, detail=detail)
            return
        if done is not None:
            job.done = done
        if job.total:
            job.progress = min(1.0, job.done / job.total)
        job.detail = detail
        await self._queue.publish(
            "job.progress",
            job_id=job.id,
            kind=job.kind,
            status=job.status.value,
            progress=job.progress,
            total=job.total,
            done=job.done,
            detail=job.detail,
        )

    async def _publish_step(self, job: Job, source: CompiledSource, step: str) -> None:
        """在标准任务事件中附加 source/step，便于围观页显示步骤。"""

        await self._queue.publish(
            "job.progress",
            job_id=job.id,
            kind=job.kind,
            status=job.status.value,
            progress=job.progress,
            total=job.total,
            done=job.done,
            detail=f"{source.title} · {step}",
            source_id=source.source_id,
            step=step,
        )


def _parse_llm_payload(raw_output: str) -> dict[str, Any]:
    """解析 JSON；即使模型误加代码围栏也只做最小清理。"""

    text = raw_output.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            text = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError(
            ErrorCode.PARSE_FAILED,
            "LLM 输出不是有效 JSON",
            {"detail": str(exc)},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(ErrorCode.PARSE_FAILED, "LLM JSON 根节点必须是对象")
    return payload


def _validate_summary(payload: dict[str, Any]) -> tuple[str, str, str, str]:
    """校验摘要页字段并返回规范化页面名。"""

    summary = payload.get("summary_page")
    if not isinstance(summary, dict):
        raise AppError(ErrorCode.PARSE_FAILED, "LLM JSON 缺少 summary_page 对象")
    title = str(summary.get("title", "")).strip()
    zone = str(summary.get("zone", "")).strip() or "未分区"
    content = str(summary.get("content", "")).strip()
    normalized = normalize_page_name(title)
    if not title or not normalized or not content:
        raise AppError(ErrorCode.PARSE_FAILED, "summary_page 的 title/content 不能为空")
    return normalized, title, zone, content


def _child_list(payload: dict[str, Any], key: str) -> list[Any]:
    """校验概念/实体数组字段。"""

    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise AppError(ErrorCode.PARSE_FAILED, f"{key} 必须是数组")
    return value


def _validate_child(item: Any, page_type: PageType) -> tuple[str, str]:
    """校验概念/实体页字段。"""

    if not isinstance(item, dict):
        raise AppError(ErrorCode.PARSE_FAILED, f"{page_type.value} 页面必须是对象")
    title = str(item.get("title", "")).strip()
    content = str(item.get("content", "")).strip()
    normalized = normalize_page_name(title)
    if not title or not normalized or not content:
        raise AppError(ErrorCode.PARSE_FAILED, f"{page_type.value} 页面的 title/content 不能为空")
    links = item.get("links", [])
    if links is not None and not isinstance(links, list):
        raise AppError(ErrorCode.PARSE_FAILED, "links 必须是字符串数组")
    if links and any(not isinstance(link, str) or not link.strip() for link in links):
        raise AppError(ErrorCode.PARSE_FAILED, "links 不能包含空字符串")
    return normalized, title


def _with_links(
    content: str,
    *,
    declared_links: list[Any],
    required_links: list[str],
) -> str:
    """补齐互链，保证 frontmatter links 和正文 [[链接]] 保持一致。"""

    existing = {
        normalize_page_name(link.target)
        for link in extract_links(content)
    }
    missing: list[str] = []
    for raw in [*declared_links, *required_links]:
        target = normalize_page_name(str(raw))
        if target and target not in existing and target not in missing:
            missing.append(target)
    if not missing:
        return content
    links_text = " ".join(f"[[{target}]]" for target in missing)
    return f"{content}\n\n**相关页面**：{links_text}\n"


def _append_contradictions(content: str, contradictions: list[Any]) -> str:
    """先把矛盾作为摘要页记录，完整增量标记由 TASK-014 扩展。"""

    valid: list[tuple[str, str]] = []
    for item in contradictions:
        if not isinstance(item, dict):
            raise AppError(ErrorCode.PARSE_FAILED, "contradictions 项必须是对象")
        page = normalize_page_name(str(item.get("page", "")))
        reason = str(item.get("reason", "")).strip()
        if not page or not reason:
            raise AppError(ErrorCode.PARSE_FAILED, "contradictions 的 page/reason 不能为空")
        valid.append((page, reason))
    if not valid:
        return content
    lines = ["", "## 矛盾记录", ""]
    lines.extend(f"- [[{page}]]：{reason}" for page, reason in valid)
    return content + "\n" + "\n".join(lines) + "\n"
