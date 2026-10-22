from __future__ import annotations

import json
from typing import Any

from .sse import SSEParser

MAX_EVENT_JSON_BYTES = 1_000_000


def _token_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def estimate_text_tokens(text_chars: int) -> int:
    return -(-text_chars // 4) if text_chars > 0 else 0


def _content_chars(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(
            len(p["text"])
            for p in content
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        )
    return 0


def estimate_prompt_tokens(body: bytes, content_type: str | None) -> int:
    """Rough prompt size from a JSON request. Returns 0 when the body is not understood."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    if (
        not body
        or len(body) > 5_000_000
        or not (ctype == "application/json" or ctype.endswith("+json"))
    ):
        return 0
    try:
        data = json.loads(body)
    except (ValueError, RecursionError):
        return 0
    if not isinstance(data, dict):
        return 0
    total = 0
    messages = data.get("messages")
    if isinstance(messages, list):
        total += 3
        for message in messages:
            if isinstance(message, dict):
                role = message.get("role")
                total += 4 + estimate_text_tokens(len(role) if isinstance(role, str) else 0)
                total += estimate_text_tokens(_content_chars(message.get("content")))
    for key in ("input", "prompt"):
        value = data.get(key)
        if isinstance(value, str):
            total += estimate_text_tokens(len(value))
    return total


class StreamTap:
    """Watches a server-sent-event stream and keeps only counts. No text is retained."""

    def __init__(self) -> None:
        self._parser = SSEParser()
        self.usage: dict[str, int] | None = None
        self.text_chars = 0
        self.done = False
        self.error_event = False
        self.model: str | None = None

    def feed(self, chunk: bytes) -> None:
        try:
            for event in self._parser.feed(chunk):
                self._handle(event.event, event.data)
        except Exception:
            return

    def finish(self) -> None:
        try:
            for event in self._parser.finish():
                self._handle(event.event, event.data)
        except Exception:
            return

    def _handle(self, event: str, data: str) -> None:
        if data.strip() == "[DONE]":
            self.done = True
            return
        if event == "error":
            self.error_event = True
        if len(data) > MAX_EVENT_JSON_BYTES:
            return
        try:
            obj = json.loads(data)
        except (ValueError, RecursionError):
            return
        if not isinstance(obj, dict):
            return
        if "error" in obj and obj["error"]:
            self.error_event = True
        if self.model is None and isinstance(obj.get("model"), str):
            self.model = obj["model"][:128]
        usage = obj.get("usage")
        if not isinstance(usage, dict) and isinstance(obj.get("response"), dict):
            usage = obj["response"].get("usage")
        if isinstance(usage, dict):
            self._take_usage(usage)
        choices = obj.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                delta = choice.get("delta") if isinstance(choice, dict) else None
                if isinstance(delta, dict):
                    self.text_chars += _content_chars(delta.get("content"))
        if isinstance(obj.get("delta"), str):
            self.text_chars += len(obj["delta"])

    def _take_usage(self, usage: dict[str, Any]) -> None:
        prompt = _token_count(usage.get("prompt_tokens", usage.get("input_tokens")))
        completion = _token_count(usage.get("completion_tokens", usage.get("output_tokens")))
        if prompt is None and completion is None:
            return
        found: dict[str, int] = {"prompt_tokens": prompt or 0, "completion_tokens": completion or 0}
        details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details")
        if isinstance(details, dict):
            cached = _token_count(details.get("cached_tokens"))
            if cached is not None:
                found["cached_prompt_tokens"] = cached
        self.usage = found
