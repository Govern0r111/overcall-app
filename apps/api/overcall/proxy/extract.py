from __future__ import annotations

import hashlib
import json
from typing import Any

MAX_PARSE_BYTES = 5_000_000
CONTEXT_MIN_CHARS = 200


def _is_json(content_type: str | None) -> bool:
    ctype = (content_type or "").split(";")[0].strip().lower()
    return ctype == "application/json" or ctype.endswith("+json")


def _load(body: bytes, content_type: str | None) -> Any:
    if not body or len(body) > MAX_PARSE_BYTES or not _is_json(content_type):
        return None
    try:
        return json.loads(body)
    except (ValueError, RecursionError):
        return None


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        )
    return ""


def extract_openai_request(body: bytes, content_type: str | None) -> dict[str, Any]:
    data = _load(body, content_type)
    out: dict[str, Any] = {}
    if not isinstance(data, dict):
        return out
    if isinstance(data.get("model"), str):
        out["model"] = data["model"][:128]
    out["stream"] = data.get("stream") is True
    out["uses_tools"] = bool(data.get("tools") or data.get("functions"))
    messages = data.get("messages")
    if isinstance(messages, list):
        context = "".join(
            _text(m.get("content"))
            for m in messages
            if isinstance(m, dict) and m.get("role") in ("system", "developer")
        )
        if len(context) >= CONTEXT_MIN_CHARS:
            out["context_hash"] = hashlib.sha256(context.encode()).hexdigest()[:16]
            out["context_tokens"] = -(-len(context) // 4)
    return out


def extract_openai_response(body: bytes, content_type: str | None) -> dict[str, Any]:
    data = _load(body, content_type)
    out: dict[str, Any] = {}
    if not isinstance(data, dict):
        return out
    usage = data.get("usage")
    if isinstance(usage, dict):
        for src, dst in (
            ("prompt_tokens", "prompt_tokens"),
            ("completion_tokens", "completion_tokens"),
        ):
            value = usage.get(src)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                out[dst] = value
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            cached = details.get("cached_tokens")
            if isinstance(cached, int) and not isinstance(cached, bool) and cached >= 0:
                out["cached_prompt_tokens"] = cached
    if isinstance(data.get("model"), str) and "model" not in out:
        out["model"] = data["model"][:128]
    return out


def extract_stripe(query: dict[str, str], body: bytes, content_type: str | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    limit = query.get("limit")
    if limit and limit.isdigit():
        out["list_limit"] = int(limit)
    data = _load(body, content_type)
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        out["items_returned"] = len(data["data"])
    return out
