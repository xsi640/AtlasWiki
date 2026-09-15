"""体检触发、忽略与结构性修复服务（TASK-030）。"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from llmwiki.config import ConfigStore, config_store
from llmwiki.errors import AppError, ErrorCode
from llmwiki.jobs import Job, JobQueue, job_queue
from llmwiki.schema import PageType
from llmwiki.workspace.store import Page, WikiStore, atomic_write_bytes

from .scanner import LintScanner
from .store import merge_ignored, read_report, report_path, utc_now, write_report


class LintService:
    """封装体检任务、报告写入与最小侵入的结构修复。"""

    def __init__(
        self,
        *,
        scanner: LintScanner | None = None,
        queue: JobQueue = job_queue,
        config_store_override: ConfigStore | None = None,
    ) -> None:
        self._scanner = scanner or LintScanner()
        self._queue = queue
        self._config = config_store_override

    @property
    def config_store(self) -> ConfigStore:
        """返回注入配置仓库或全局冻结单例。"""

        return self._config or config_store

    @property
    def queue(self) -> JobQueue:
        """返回注入任务队列，便于测试断言。"""

        return self._queue

    async def run_lint(self) -> Job:
        """提交一次只读扫描任务。"""

        vault_path = self._vault_path()
        return await self._queue.submit("lint", lambda job: self.scan_and_save(job, vault_path), total=1)

    async def get_report(self) -> dict[str, Any]:
        """获取报告；首次访问时立即做一次只读扫描并落盘。"""

        vault_path = self._vault_path()
        report = read_report(vault_path)
        if report is not None:
            return report
        issues = merge_ignored(await self._scanner.scan(vault_path), None)
        return write_report(vault_path, issues, graph_metrics=self._graph_metrics(vault_path))

    async def scan_and_save(self, job: Job, vault_path: str | Path) -> dict[str, Any]:
        """队列回调：扫描、合并 ignore 状态并原子写报告。"""

        if self._owns(job):
            await self._queue.update_progress(job, detail="正在扫描知识库")
        issues = await self._scanner.scan(vault_path)
        issues = merge_ignored(issues, read_report(vault_path))
        graph_metrics = self._graph_metrics(vault_path)
        report = write_report(vault_path, issues, graph_metrics=graph_metrics)
        await self._queue.publish(
            "lint.ready",
            job_id=job.id,
            issue_count=len(issues),
            repairable_count=sum(issue["repairable"] and not issue["ignored"] for issue in issues),
        )
        if self._owns(job):
            await self._queue.update_progress(job, done=1, detail="体检完成")
        return report

    async def ignore_issue(self, issue_id: str, reason: str) -> dict[str, Any]:
        """在已有报告上记录忽略原因；不修改 wiki 页面。"""

        if not reason.strip():
            raise AppError(
                ErrorCode.VALIDATION,
                "忽略原因不能为空",
                {"fields": [{"field": "reason", "reason": "必填"}]},
            )
        vault_path = self._vault_path()
        report = self._existing_report(vault_path)
        issue = next((item for item in report.get("issues", []) if item.get("id") == issue_id), None)
        if issue is None:
            raise AppError(ErrorCode.NOT_FOUND, "体检问题不存在", {"issue_id": issue_id})

        issue["ignored"] = True
        issue["ignore_reason"] = reason.strip()
        report["generated_at"] = utc_now()
        atomic_write_bytes(report_path(vault_path), json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
        return {"ok": True, "issue": issue}

    async def fix_issue(self, issue_id: str) -> Job:
        """只允许提交结构性问题修复；语义类问题直接拒绝。"""

        vault_path = self._vault_path()
        report = self._existing_report(vault_path)
        issue = next((item for item in report.get("issues", []) if item.get("id") == issue_id), None)
        if issue is None:
            raise AppError(ErrorCode.NOT_FOUND, "体检问题不存在", {"issue_id": issue_id})
        if not issue.get("repairable", False):
            raise AppError(
                ErrorCode.VALIDATION,
                "语义类问题不能自动修复",
                {"issue_id": issue_id, "kind": issue.get("kind")},
            )
        return await self._queue.submit("lint-fix", lambda job: self._fix_in_job(job, vault_path, issue_id), total=1)

    async def idle_check(self, *, force: bool = False, idle_minutes: int = 30) -> Job | None:
        """闲置触发入口：报告超过窗口且没有体检任务时才提交。"""

        if self._lint_busy():
            return None
        vault_path = self._vault_path()
        if not force and not self._is_stale(vault_path, idle_minutes):
            return None
        return await self.run_lint()

    async def _fix_in_job(self, job: Job, vault_path: str | Path, issue_id: str) -> None:
        if self._owns(job):
            await self._queue.update_progress(job, detail="正在修复结构问题")

        latest = await self._scanner.scan(vault_path)
        issue = next((item for item in latest if item["id"] == issue_id), None)
        manual_required = False
        if issue is not None:
            store = WikiStore(vault_path)
            page = store.read_page(issue["page"])
            manual_required = page.metadata.get("human_edited") is True
            if issue["kind"] == "missing_index":
                self._rebuild_index(store, store.read_pages())
            elif issue["kind"] == "dead_link" and not manual_required:
                target = self._dead_target(issue)
                content = self._remove_dead_link(page.content, target)
                store.write_markdown(page.relative_path, dict(page.metadata), content, update_timestamp=True)

        issues = merge_ignored(await self._scanner.scan(vault_path), read_report(vault_path))
        if manual_required:
            issues = [self._mark_manual(item) if item["id"] == issue_id else item for item in issues]
        write_report(vault_path, issues, graph_metrics=self._graph_metrics(vault_path))
        if self._owns(job):
            detail = "已标注需人工处理" if manual_required else "结构修复完成"
            await self._queue.update_progress(job, done=1, detail=detail)

    @staticmethod
    def _mark_manual(issue: dict[str, Any]) -> dict[str, Any]:
        """保留 human_edited 页面的结构问题，并明确标注不能自动覆盖。"""

        return {
            **issue,
            "manual_required": True,
            "suggestion": "页面为人工编辑，需人工确认后修改链接",
        }

    @staticmethod
    def _dead_target(issue: dict[str, Any]) -> str:
        """从稳定描述中提取失效目标；报告若被改动则拒绝修复。"""

        match = re.search(r"\[\[([^\]]+)\]", issue["detail"])
        if match is None:
            raise AppError(ErrorCode.VALIDATION, "失效链接信息不完整", {"issue": issue})
        return match.group(1)

    @staticmethod
    def _remove_dead_link(content: str, target: str) -> str:
        """把失效 wiki 链接还原为显示文本或页面名。"""

        pattern = re.compile(rf"\[\[{re.escape(target)}(?:\|([^\]]+))?\]\]")
        return pattern.sub(lambda match: match.group(1) or target, content)

    @staticmethod
    def _rebuild_index(store: WikiStore, pages: list[Page]) -> None:
        """重建轻量索引；不会修改任何被索引页面。"""

        lines = ["# 页面索引", "", "| 页面 | 类型 | 分区 | 摘要 |", "| --- | --- | --- | --- |"]
        for page in sorted(pages, key=lambda item: item.name):
            page_type = page.metadata.get("type", PageType.CONCEPT.value)
            first_line = next(
                (line.strip().lstrip("# ").strip() for line in page.content.splitlines() if line.strip()),
                "",
            )
            lines.append(
                f"| [[{page.name}]] | {page_type} "
                f"| {page.metadata.get('zone', '')} | {first_line.replace('|', '\\|')} |"
            )
        store.write_markdown(
            "wiki/index.md",
            {
                "title": "页面索引",
                "type": PageType.ANALYSIS.value,
                "source_type": "compiled",
                "zone": "系统",
                "human_edited": False,
                "status": "active",
            },
            "\n".join(lines) + "\n",
            update_timestamp=True,
        )

    def _graph_metrics(self, vault_path: str | Path) -> dict[str, float | int]:
        """供报告层写入 SC-3 指标；页面读取仍是只读操作。"""

        store = WikiStore(vault_path)
        pages = store.read_pages() if store.initialized else []
        index = store.link_index() if pages else None
        return self._scanner.metrics(pages, index) if index else {
            "page_count": 0,
            "orphan_count": 0,
            "orphan_ratio": 0.0,
            "average_out_links": 0.0,
        }

    def _owns(self, job: Job) -> bool:
        return self._queue.get(job.id) is job

    def _lint_busy(self) -> bool:
        return any(
            job.kind in {"lint", "lint-fix"} and job.status.value in {"queued", "running"}
            for job in self._queue.jobs
        )

    @staticmethod
    def _is_stale(vault_path: str | Path, idle_minutes: int) -> bool:
        report = read_report(vault_path)
        if not report:
            return True
        try:
            generated = datetime.fromisoformat(str(report["generated_at"]).replace("Z", "+00:00"))
            return time.time() - generated.timestamp() >= idle_minutes * 60
        except (KeyError, TypeError, ValueError):
            return True

    def _vault_path(self) -> Path:
        value = self.config_store.load().vault_path
        if not value:
            raise AppError(
                ErrorCode.VALIDATION,
                "尚未配置 vault 路径",
                {"fields": [{"field": "vault_path", "reason": "必填"}]},
            )
        return Path(value).expanduser().resolve()

    def _existing_report(self, vault_path: str | Path) -> dict[str, Any]:
        report = read_report(vault_path)
        if report is None:
            raise AppError(ErrorCode.NOT_FOUND, "体检报告不存在，请先运行体检")
        return report


async def idle_check() -> Job | None:
    """模块级闲置触发接口，便于应用装配层直接调用。"""

    return await LintService().idle_check()
