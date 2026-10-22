from __future__ import annotations

import hashlib
import json
import re
from typing import Any

WORDS = (
    "the", "request", "was", "handled", "by", "a", "careful", "cache", "layer", "while",
    "costs", "stayed", "low", "and", "latency", "remained", "steady", "across", "many",
    "calls", "retry", "policy", "prefers", "backoff", "over", "bursts", "models", "answer",
    "quickly", "when", "prompts", "are", "short", "batch", "work", "together", "to", "save",
    "tokens", "every", "day",
)  # fmt: skip

MAX_PAD_BYTES = 5_000_000


def count_tokens(text: str) -> int:
    """Rough token estimate (about four characters per token). Deterministic and offline."""
    if not text:
        return 0
    return -(-len(text) // 4)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part["text"]
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return ""


def count_message_tokens(messages: list[dict[str, Any]]) -> int:
    total = 3
    for message in messages:
        total += (
            4
            + count_tokens(message.get("role", ""))
            + count_tokens(_content_text(message.get("content")))
        )
    return total


def request_seed(payload: dict[str, Any]) -> bytes:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).digest()


def generate_text(seed: bytes, index: int, max_tokens: int | None) -> tuple[str, str]:
    """Return (text, finish_reason). The same seed and index always give the same text."""
    head = hashlib.sha256(seed + index.to_bytes(2, "big")).digest()
    word_count = 12 + head[0] % 40
    words = [
        WORDS[hashlib.sha256(seed + index.to_bytes(2, "big") + i.to_bytes(2, "big")).digest()[0]
              % len(WORDS)]
        for i in range(word_count)
    ]  # fmt: skip
    text = " ".join(words).capitalize() + "."
    if max_tokens is not None and count_tokens(text) > max_tokens:
        return text[: max_tokens * 4].rstrip(), "length"
    return text, "stop"


def embedding_vector(seed: bytes, index: int, dimensions: int) -> list[float]:
    raw: list[float] = []
    counter = 0
    while len(raw) < dimensions:
        block = hashlib.sha256(seed + index.to_bytes(4, "big") + counter.to_bytes(4, "big"))
        raw.extend(byte / 127.5 - 1.0 for byte in block.digest())
        counter += 1
    raw = raw[:dimensions]
    norm = sum(value * value for value in raw) ** 0.5 or 1.0
    return [round(value / norm, 8) for value in raw]


def split_stream_pieces(text: str) -> list[str]:
    return re.findall(r"\S+\s*", text) or [text]
