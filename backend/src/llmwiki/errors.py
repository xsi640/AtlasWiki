"""统一错误码与异常类型（契约层，所有模块只 import，不修改）。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """API 统一错误码，与 api-design.md §1.4 / tech-architecture.md §6.2 一一对应。"""

    VALIDATION = "E_VALIDATION"
    NOT_FOUND = "E_NOT_FOUND"
    DUPLICATE_SOURCE = "E_DUPLICATE_SOURCE"
    PARSE_FAILED = "E_PARSE_FAILED"
    SOURCE_BUSY = "E_SOURCE_BUSY"
    LLM_NOT_CONFIGURED = "E_LLM_NOT_CONFIGURED"
    LLM_AUTH = "E_LLM_AUTH"
    LLM_TIMEOUT = "E_LLM_TIMEOUT"
    LLM_RATE_LIMIT = "E_LLM_RATE_LIMIT"
    JOB_CONFLICT = "E_JOB_CONFLICT"
    PATH_OUT_OF_VAULT = "E_PATH_OUT_OF_VAULT"
    GIT_FAILED = "E_GIT_FAILED"


STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.DUPLICATE_SOURCE: 409,
    ErrorCode.PARSE_FAILED: 422,
    ErrorCode.SOURCE_BUSY: 409,
    ErrorCode.LLM_NOT_CONFIGURED: 503,
    ErrorCode.LLM_AUTH: 502,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.LLM_RATE_LIMIT: 429,
    ErrorCode.JOB_CONFLICT: 409,
    ErrorCode.PATH_OUT_OF_VAULT: 400,
    ErrorCode.GIT_FAILED: 502,
}


class AppError(Exception):
    """业务异常基类，由 API 层捕获后转为统一 JSON 错误响应。"""

    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    @property
    def status_code(self) -> int:
        return STATUS_MAP.get(self.code, 500)

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code.value, "message": self.message, "details": self.details}}
