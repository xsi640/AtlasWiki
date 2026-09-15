"""跨页问答引擎（TASK-026）。"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llmwiki.config import config_store
from llmwiki.errors import AppError, ErrorCode
from llmwiki.jobs import Job
from llmwiki.llm import complete
from llmwiki.schema import QUERY_PROMPT, normalize_page_name
from llmwiki.workspace.links import extract_links
from llmwiki.workspace.store import WikiStore

from .store import QueryStore, utc_now

_MAX_CANDIDATES = 10
_ENGLISH_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "what",
    "how",
    "why",
    "which",
    "who",
    "when",
    "where",
    "是",
    "的",
    "了",
    "吗",
    "怎么",
    "什么",
    "哪些",
    "如何",
    "为什么",
}


@dataclass
class _Candidate:
    name: str
    title: str
    text: str
    score: float


class LlmClient:
    """最小 LLM 客户端适配器，保持可替换测试边界。"""

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        job_id: str | None = None,
    ) -> str:
        """委托全局 OpenAI-compatible 客户端。"""

        return await complete(
            messages,
            json_mode=json_mode,
            operation="ask",
            job_id=job_id,
        )


class AskEngine:
    """候选页选取、LLM 综合作答与问答历史落盘。"""

    def __init__(
        self,
        *,
        llm_client: Any | None = None,
        config_store_override: Any | None = None,
    ) -> None:
        self.llm_client = llm_client or LlmClient()
        self.config_store = config_store_override or config_store

    @staticmethod
    def _tokens(question: str) -> list[str]:
        """提取中英文问题关键词，中文补充二阶切分提升简单匹配能力。"""

        lowered = question.lower()
        words = [
            word.lower() for word in _ENGLISH_RE.findall(lowered) if word.lower() not in _STOP_WORDS
        ]
        cjk_phrases: list[str] = []
        for phrase in _CJK_RE.findall(question):
            cjk_phrases.append(phrase)
            if len(phrase) > 2:
                cjk_phrases.extend(phrase[index : index + 2] for index in range(len(phrase) - 1))
        return list(dict.fromkeys(words + cjk_phrases))

    @staticmethod
    def _score(page_name: str, title: str, content: str, tokens: list[str]) -> float:
        title_text = f"{page_name} {title}".lower()
        content_text = content.lower()
        score = 0.0
        for token in tokens:
            token = token.lower()
            if not token:
                continue
            occurrences = content_text.count(token)
            score += occurrences
            score += title_text.count(token) * 8
        return score

    def select_candidates(self, pages: list[Any], question: str) -> list[_Candidate]:
        """按关键词命中选取相关页，标题权重更高。"""

        tokens = self._tokens(question)
        candidates: list[_Candidate] = []
        for page in pages:
            title = str(page.metadata.get("title", page.name))
            score = self._score(page.name, title, page.content, tokens)
            if score > 0:
                candidates.append(
                    _Candidate(name=page.name, title=title, text=page.content, score=score)
                )
        candidates.sort(key=lambda item: (-item.score, item.name))
        return candidates[:_MAX_CANDIDATES]

    @staticmethod
    def _page_context(candidates: list[_Candidate]) -> str:
        if not candidates:
            return "（知识库中没有匹配页面）"
        chunks = []
        for candidate in candidates:
            chunks.append(f"# [[{candidate.name}]]\n{candidate.text.strip()}")
        return "\n\n---\n\n".join(chunks)

    @staticmethod
    def _parse_llm_output(output: str) -> tuple[str, bool, list[dict[str, str]]]:
        """兼容 JSON 与纯文本；JSON 可携带 insufficient / related_pages。"""

        text = output.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text, "知识不足" not in text, []
        if not isinstance(payload, dict):
            return text, "知识不足" not in text, []
        answer = str(payload.get("answer") or payload.get("content") or "").strip()
        sufficient = bool(payload.get("sufficient", not payload.get("insufficient", False)))
        related: list[dict[str, str]] = []
        for item in payload.get("related_pages", []):
            if isinstance(item, str):
                related.append({"name": item, "title": item})
            elif isinstance(item, dict) and item.get("name"):
                related.append(
                    {
                        "name": str(item["name"]),
                        "title": str(item.get("title", item["name"])),
                    }
                )
        return answer or text, sufficient, related

    @staticmethod
    def _normalize_related(
        related: list[dict[str, str]],
        participating: dict[str, str],
    ) -> list[dict[str, str]]:
        output: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in related:
            name = normalize_page_name(str(item.get("name", "")))
            if not name or name in seen or name not in participating:
                continue
            seen.add(name)
            output.append({"name": name, "title": participating[name]})
        return output[:5]

    @staticmethod
    def _citations(answer: str, participating: dict[str, str]) -> list[dict[str, str]]:
        citations: list[dict[str, str]] = []
        seen: set[str] = set()
        for link in extract_links(answer):
            name = normalize_page_name(link.target)
            if name in seen or name not in participating:
                continue
            seen.add(name)
            citations.append(
                {
                    "page": name,
                    "title": participating[name],
                    "anchor_text": link.label,
                }
            )
        return citations

    @staticmethod
    async def _last_cost(costs: list[dict[str, Any]], job_id: str) -> float:
        values = [
            float(item.get("cost", 0))
            for item in costs
            if item.get("job_id") == job_id and item.get("operation") == "ask"
        ]
        return round(values[-1] if values else 0.0, 8)

    async def ask(self, job: Job, vault_path: str | Path, question: str) -> dict[str, Any]:
        """执行一次问答并写入 `queries.json`。"""

        clean_question = str(question).strip()
        if not clean_question:
            raise AppError(
                ErrorCode.VALIDATION,
                "问题不能为空",
                {"fields": [{"field": "question", "reason": "必填"}]},
            )
        if not self.config_store.load().llm.api_key.strip():
            raise AppError(
                ErrorCode.LLM_NOT_CONFIGURED,
                "LLM API key 未配置",
                {"operation": "ask"},
            )

        store = WikiStore(Path(vault_path).expanduser().resolve())
        if not store.initialized:
            raise AppError(ErrorCode.NOT_FOUND, "vault 不存在或尚未初始化")
        pages = await asyncio.to_thread(store.read_pages)
        candidates = self.select_candidates(pages, clean_question)
        prompt = (
            QUERY_PROMPT.format(pages=self._page_context(candidates), question=clean_question)
            + '\n\n请只输出 JSON：{"answer":"...","sufficient":true,'
            + '"related_pages":[{"name":"...","title":"..."}]}'
        )
        messages = [
            {"role": "user", "content": prompt},
        ]
        job.detail = "正在跨页综合作答"
        job.progress = 0.2

        raw_answer = await self.llm_client.complete(
            messages,
            json_mode=True,
            job_id=job.id,
        )
        answer, sufficient, related = self._parse_llm_output(str(raw_answer))
        participating = {item.name: item.title for item in candidates}
        if not sufficient:
            answer = answer or "当前知识库知识不足，无法充分回答该问题。"
            if "不足" not in answer:
                answer = f"当前知识库知识不足，无法充分回答该问题。\n\n{answer}"
        citations = self._citations(answer, participating)
        fallback_related = [{"name": item.name, "title": item.title} for item in candidates]
        related_pages = self._normalize_related(related or fallback_related, participating)

        record = {
            "id": "",
            "job_id": job.id,
            "question": clean_question,
            "answer": answer,
            "sufficient": sufficient,
            "citations": citations,
            "related_pages": related_pages,
            "pages_considered": len(candidates),
            "cost": {"currency": "USD", "total": await self._cost(job.id)},
            "created_at": utc_now(),
            "saved_page": None,
        }
        query_store = QueryStore(store.vault)
        persisted = await query_store.append(record)
        job.detail = "问答完成"
        job.progress = 1.0
        job.done = 1
        return persisted

    async def _cost(self, job_id: str) -> float:
        from llmwiki.llm import get_costs

        return await self._last_cost(await get_costs(), job_id)
