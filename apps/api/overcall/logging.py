from __future__ import annotations

import contextvars
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)basic\s+[A-Za-z0-9+/=]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"\boc_[A-Za-z0-9_-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),
    re.compile(
        r"""(?i)(authorization|x-api-key|api[-_]?key|secret|password|token)["']?\s*[:=]\s*["']?[^\s"',}]{6,}"""
    ),
]


def redact(value: Any) -> str:
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def set_request_id(value: str) -> contextvars.Token[str]:
    return _request_id.set(value)


def reset_request_id(token: contextvars.Token[str]) -> None:
    _request_id.reset(token)


def get_request_id() -> str:
    return _request_id.get()


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
        except Exception:
            record.msg = "[unformattable log message]"
        record.args = ()
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": get_request_id(),
            "message": redact(record.getMessage()),
        }
        if record.exc_text:
            payload["exception"] = redact(record.exc_text)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    for logger_name in logging.root.manager.loggerDict:
        configured_logger = logging.getLogger(logger_name)
        for handler in configured_logger.handlers:
            if not any(isinstance(item, RedactionFilter) for item in handler.filters):
                handler.addFilter(RedactionFilter())
            handler.setFormatter(JsonFormatter())
    for handler in root.handlers:
        if not any(isinstance(item, RedactionFilter) for item in handler.filters):
            handler.addFilter(RedactionFilter())
        handler.setFormatter(JsonFormatter())
    root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True
