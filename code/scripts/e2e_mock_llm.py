"""端到端验证用的 OpenAI 兼容 mock LLM 服务器（仅标准库）。

按 system 提示词区分三类请求，返回确定性的 JSON 结果：
- 「分段摘要器」→ 长文分段摘要（TASK-015）
- 「知识编译引擎」→ INGEST_PROMPT 要求的完整编译 JSON
- 其余（问答 QUERY_PROMPT）→ {"answer", "sufficient", "related_pages"}

用法：python e2e_mock_llm.py --port 0  # 打印实际端口到 stdout
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COMPILE_OUTPUT = {
    "summary_page": {
        "title": "测试素材摘要",
        "zone": "测试分区",
        "content": "本素材讨论了测试概念的形成，并提到测试实体的例子。",
    },
    "concept_pages": [
        {
            "title": "测试概念",
            "zone": "测试分区",
            "content": "测试概念是从素材中提炼出的核心思想。",
            "links": ["测试素材摘要"],
        }
    ],
    "entity_pages": [
        {
            "title": "测试实体",
            "zone": "测试分区",
            "content": "测试实体是素材中举出的具体事物。",
            "links": ["测试素材摘要"],
        }
    ],
    "contradictions": [],
}

SEGMENT_OUTPUT = {
    "summary": "本段要点：素材片段讨论测试概念与测试实体。",
    "concepts": ["测试概念"],
    "entities": ["测试实体"],
}

ASK_OUTPUT = {
    "answer": "根据知识库，[[测试概念]] 是从素材中提炼的核心思想，出处见 [[测试素材摘要]]。",
    "sufficient": True,
    "related_pages": [{"name": "测试概念", "title": "测试概念"}],
}


def _answer_for(messages: list[dict[str, str]]) -> dict | str:
    system_prompt = ""
    for message in messages:
        if str(message.get("role", "")) == "system":
            system_prompt = str(message.get("content", ""))
            break

    if "分段摘要器" in system_prompt:
        return SEGMENT_OUTPUT
    if "知识编译引擎" in system_prompt:
        return COMPILE_OUTPUT
    # 问答（QUERY_PROMPT）与其余请求统一返回 sufficiency 答案。
    return ASK_OUTPUT


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")

        match = re.search(r"/chat/completions/?$", self.path)
        if not match:
            self._send_json({"error": {"message": f"unknown path {self.path}"}}, status=404)
            return

        messages = list(body.get("messages", []))
        content = json.dumps(_answer_for(messages), ensure_ascii=False)
        self._send_json(
            {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "model": body.get("model", "mock-model"),
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 32, "completion_tokens": 64, "total_tokens": 96},
            }
        )

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/").endswith("/healthz"):
            self._send_json({"ok": True})
            return
        self._send_json({"error": {"message": f"unknown path {self.path}"}}, status=404)

    def _send_json(self, payload: dict, *, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args) -> None:  # 静默访问日志
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), MockHandler)
    print(server.server_address[1], flush=True)  # 端口作为协议交给调用方
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
