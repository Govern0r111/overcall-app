from __future__ import annotations

import json
import random

import pytest

from overcall.proxy.sse import SSEParser
from overcall.proxy.tokens import StreamTap, estimate_prompt_tokens, estimate_text_tokens

CHUNKS = [
    {"id": "c1", "model": "gpt-4o-mini", "choices": [{"index": 0, "delta": {"role": "assistant"}}]},
    {"id": "c1", "choices": [{"index": 0, "delta": {"content": "héllo ✓ "}}], "usage": None},
    {"id": "c1", "choices": [{"index": 0, "delta": {"content": "wörld"}}]},
    {
        "id": "c1",
        "choices": [],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 4,
            "prompt_tokens_details": {"cached_tokens": 3},
        },
    },
]


def stream_bytes(newline: bytes = b"\n") -> bytes:
    out = b": keep-alive" + newline + newline
    for chunk in CHUNKS:
        out += b"data: " + json.dumps(chunk, ensure_ascii=False).encode() + newline + newline
    return out + b"data: [DONE]" + newline + newline


def parse_in_pieces(data: bytes, cuts: list[int]) -> list[tuple[str, str]]:
    parser = SSEParser()
    events = []
    previous = 0
    for cut in [*cuts, len(data)]:
        events += parser.feed(data[previous:cut])
        previous = cut
    events += parser.finish()
    return [(e.event, e.data) for e in events]


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
def test_every_split_position_gives_identical_events(newline):
    data = stream_bytes(newline)
    expected = parse_in_pieces(data, [])
    assert len(expected) == len(CHUNKS) + 1 and expected[-1][1] == "[DONE]"
    for position in range(len(data) + 1):
        assert parse_in_pieces(data, [position]) == expected


def test_random_splits_and_single_byte_feed_are_identical():
    data = stream_bytes(b"\r\n")
    expected = parse_in_pieces(data, [])
    rng = random.Random(7)
    for _ in range(300):
        cuts = sorted(rng.sample(range(len(data)), rng.randint(1, 12)))
        assert parse_in_pieces(data, cuts) == expected
    assert parse_in_pieces(data, list(range(1, len(data)))) == expected


def test_parser_edge_cases():
    parse = lambda raw: parse_in_pieces(raw, [])  # noqa: E731
    assert parse(b"data: a\ndata: b\n\n") == [("message", "a\nb")]
    assert parse(b"event: error\ndata: x\n\n") == [("error", "x")]
    assert parse(b": comment only\n\n") == []
    assert parse(b"data:nospace\n\n") == [("message", "nospace")]
    assert parse(b"data: last-without-blank-line") == [("message", "last-without-blank-line")]
    assert parse(b"id: 1\nretry: 5\ndata: x\n\n") == [("message", "x")]


def test_oversized_line_is_dropped_not_buffered_forever():
    parser = SSEParser()
    parser.feed(b"data: " + b"x" * 1_100_000)
    assert parser.overflowed
    assert [e.data for e in parser.feed(b"\n\ndata: ok\n\n")] == ["ok"]


def test_tap_reads_usage_text_and_model_without_keeping_text():
    tap = StreamTap()
    data = stream_bytes()
    for index in range(0, len(data), 5):
        tap.feed(data[index : index + 5])
    tap.finish()
    assert tap.done and tap.usage == {
        "prompt_tokens": 11,
        "completion_tokens": 4,
        "cached_prompt_tokens": 3,
    }
    assert tap.text_chars == len("héllo ✓ wörld") and tap.model == "gpt-4o-mini"
    assert not any(isinstance(v, str) and "wörld" in v for v in vars(tap).values())


def test_tap_handles_responses_api_usage_error_and_n_choices():
    tap = StreamTap()
    tap.feed(b'data: {"type":"response.output_text.delta","delta":"abcd"}\n\n')
    tap.feed(b'data: {"response":{"usage":{"input_tokens":9,"output_tokens":2}}}\n\n')
    tap.feed(b'event: error\ndata: {"error":{"message":"x"}}\n\n')
    tap.feed(b'data: {"choices":[{"delta":{"content":"aa"}},{"delta":{"content":"bb"}}]}\n\n')
    assert tap.usage == {"prompt_tokens": 9, "completion_tokens": 2}
    assert tap.error_event and tap.text_chars == 8 and not tap.done


def test_tap_ignores_garbage_and_bad_usage():
    tap = StreamTap()
    tap.feed(b"data: not json\n\ndata: [1,2]\n\n")
    tap.feed(b'data: {"usage":{"prompt_tokens":-5,"completion_tokens":true}}\n\n')
    tap.finish()
    assert tap.usage is None and tap.text_chars == 0


def test_token_estimates():
    assert estimate_text_tokens(0) == 0 and estimate_text_tokens(5) == 2
    body = json.dumps({"messages": [{"role": "user", "content": "a" * 40}]}).encode()
    assert estimate_prompt_tokens(body, "application/json") == 3 + 4 + 1 + 10
    assert estimate_prompt_tokens(b"{bad", "application/json") == 0
    assert estimate_prompt_tokens(body, "text/plain") == 0
