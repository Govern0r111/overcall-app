from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
from typing import Any

import httpx
import pytest

from overcall.main import create_app
from overcall.mock_openai import MOCK_BASE_URL, create_mock_app, create_mock_client
from overcall.mock_openai.tokens import count_message_tokens, count_tokens
from overcall.mock_openai.transport import StreamingASGITransport

CHAT = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hello there"}]}


def call(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def run() -> httpx.Response:
        async with create_mock_client() as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def post(path: str, body: Any = None, headers: dict[str, str] | None = None) -> httpx.Response:
    return call("POST", path, json=body, headers=headers)


def sse_events(response: httpx.Response) -> tuple[list[dict[str, Any]], bool]:
    events, done = [], False
    for block in response.text.split("\n\n"):
        if not block.strip():
            continue
        assert block.startswith("data: "), block
        data = block.removeprefix("data: ")
        if data == "[DONE]":
            done = True
        else:
            events.append(json.loads(data))
    return events, done


def test_chat_completion_shape_and_usage() -> None:
    response = post("/v1/chat/completions", CHAT)
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert body["model"] == "gpt-4o-mini"
    choice = body["choices"][0]
    assert choice["index"] == 0
    assert choice["message"]["role"] == "assistant"
    assert choice["finish_reason"] == "stop"
    usage = body["usage"]
    assert usage["prompt_tokens"] == count_message_tokens(CHAT["messages"])
    assert usage["completion_tokens"] == count_tokens(choice["message"]["content"])
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_content_is_deterministic_but_id_varies() -> None:
    first = post("/v1/chat/completions", CHAT).json()
    time.sleep(1.1)
    second = post("/v1/chat/completions", CHAT).json()
    assert first["choices"][0]["message"]["content"] == second["choices"][0]["message"]["content"]
    assert first["id"] != second["id"]
    assert first["created"] != second["created"]
    other = post(
        "/v1/chat/completions",
        {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Something else"}]},
    ).json()
    assert other["choices"][0]["message"]["content"] != first["choices"][0]["message"]["content"]


def test_max_tokens_truncates_with_length_reason() -> None:
    body = post("/v1/chat/completions", {**CHAT, "max_tokens": 3}).json()
    assert body["choices"][0]["finish_reason"] == "length"
    assert body["usage"]["completion_tokens"] <= 3


def test_multiple_choices_unicode_and_empty_content() -> None:
    payload = {
        "model": "gpt-4o",
        "n": 3,
        "messages": [
            {"role": "user", "content": "héllo 你好 🌍"},
            {"role": "assistant", "content": ""},
        ],
    }
    body = post("/v1/chat/completions", payload).json()
    assert [c["index"] for c in body["choices"]] == [0, 1, 2]
    assert len({c["message"]["content"] for c in body["choices"]}) > 1


def test_very_long_input_is_accepted() -> None:
    payload = {**CHAT, "messages": [{"role": "user", "content": "word " * 200_000}]}
    body = post("/v1/chat/completions", payload).json()
    assert body["usage"]["prompt_tokens"] > 200_000


def test_stream_format_without_usage_chunk() -> None:
    response = post("/v1/chat/completions", {**CHAT, "stream": True})
    assert response.headers["content-type"].startswith("text/event-stream")
    events, done = sse_events(response)
    assert done and response.text.rstrip().endswith("data: [DONE]")
    assert events[0]["choices"][0]["delta"]["role"] == "assistant"
    assert events[-1]["choices"][0]["finish_reason"] == "stop"
    assert all("usage" not in event for event in events)
    assert len({event["id"] for event in events}) == 1
    assert all(event["object"] == "chat.completion.chunk" for event in events)


def test_stream_usage_chunk_only_when_requested() -> None:
    payload = {**CHAT, "stream": True, "stream_options": {"include_usage": True}}
    events, done = sse_events(post("/v1/chat/completions", payload))
    assert done
    last = events[-1]
    assert last["choices"] == []
    text = "".join(e["choices"][0]["delta"].get("content", "") for e in events[:-1] if e["choices"])
    assert last["usage"]["completion_tokens"] == count_tokens(text)
    assert last["usage"]["total_tokens"] == (
        last["usage"]["prompt_tokens"] + last["usage"]["completion_tokens"]
    )
    assert all(e["usage"] is None for e in events[:-1])

    off = {**CHAT, "stream": True, "stream_options": {"include_usage": False}}
    off_events, _ = sse_events(post("/v1/chat/completions", off))
    assert all(e["choices"] for e in off_events)


def test_stream_with_multiple_choices() -> None:
    events, done = sse_events(post("/v1/chat/completions", {**CHAT, "stream": True, "n": 2}))
    assert done
    seen = {e["choices"][0]["index"] for e in events if e["choices"]}
    assert seen == {0, 1}
    finishes = [e for e in events if e["choices"] and e["choices"][0]["finish_reason"]]
    assert len(finishes) == 2


@pytest.mark.parametrize(
    ("status", "kind"), [(429, "requests"), (500, "server_error"), (503, "server_error")]
)
def test_status_injection(status: int, kind: str) -> None:
    headers = {"X-Mock-Status": str(status), "X-Mock-Retry-After": "7"}
    response = post("/v1/chat/completions", CHAT, headers)
    assert response.status_code == status
    assert response.json()["error"]["type"] == kind
    assert response.headers["retry-after"] == "7"
    assert response.json()["error"].keys() == {"message", "type", "param", "code"}


def test_status_injection_without_retry_after_and_on_other_endpoints() -> None:
    response = post("/v1/embeddings", {"model": "m", "input": "x"}, {"X-Mock-Status": "503"})
    assert response.status_code == 503
    assert "retry-after" not in response.headers
    assert call("GET", "/v1/models", headers={"X-Mock-Status": "429"}).status_code == 429


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Mock-Status": "418"},
        {"X-Mock-Status": "abc"},
        {"X-Mock-Latency-Ms": "-1"},
        {"X-Mock-Latency-Ms": "999999"},
        {"X-Mock-Retry-After": "soon"},
        {"X-Mock-Drop-After-Chunks": "-2"},
        {"X-Mock-Resp-Bytes": "99999999999"},
    ],
)
def test_invalid_injection_headers_are_rejected(headers: dict[str, str]) -> None:
    response = post("/v1/chat/completions", CHAT, headers)
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_latency_injection() -> None:
    started = time.perf_counter()
    assert post("/v1/chat/completions", CHAT, {"X-Mock-Latency-Ms": "250"}).status_code == 200
    assert time.perf_counter() - started >= 0.24


def test_drop_after_chunks_cuts_stream_without_done() -> None:
    response = post(
        "/v1/chat/completions", {**CHAT, "stream": True}, {"X-Mock-Drop-After-Chunks": "2"}
    )
    events, done = sse_events(response)
    assert len(events) == 2
    assert not done
    zero, zero_done = sse_events(
        post("/v1/chat/completions", {**CHAT, "stream": True}, {"X-Mock-Drop-After-Chunks": "0"})
    )
    assert zero == [] and not zero_done


def test_resp_bytes_pads_response() -> None:
    plain = post("/v1/chat/completions", CHAT)
    padded = post("/v1/chat/completions", CHAT, {"X-Mock-Resp-Bytes": "50000"})
    assert len(plain.content) < 2000
    assert 50_000 <= len(padded.content) < 51_000
    big = post("/v1/chat/completions", {**CHAT, "stream": True}, {"X-Mock-Resp-Bytes": "30000"})
    assert len(big.content) >= 30_000


@pytest.mark.parametrize(
    ("payload", "param"),
    [
        ({"messages": CHAT["messages"]}, "model"),
        ({"model": "gpt-4o"}, "messages"),
        ({"model": "gpt-4o", "messages": []}, "messages"),
        ({"model": "gpt-4o", "messages": "hi"}, "messages"),
        ({"model": "gpt-4o", "messages": [{"role": "bogus", "content": "x"}]}, "messages[0]"),
        ({"model": "gpt-4o", "messages": ["x"]}, "messages[0]"),
        ({"model": "", "messages": CHAT["messages"]}, "model"),
        ({**CHAT, "n": 9}, "n"),
        ({**CHAT, "n": True}, "n"),
        ({**CHAT, "max_tokens": 0}, "max_tokens"),
        ({**CHAT, "stream_options": {"include_usage": True}}, "stream_options"),
    ],
)
def test_bad_chat_input_gives_openai_shaped_errors(payload: dict[str, Any], param: str) -> None:
    response = post("/v1/chat/completions", payload)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["type"] == "invalid_request_error"
    assert error["param"] == param
    assert error["message"]


def test_unparseable_bodies() -> None:
    for content in (b"not json", b"[1,2]", b""):
        response = call("POST", "/v1/chat/completions", content=content)
        assert response.status_code == 400
        assert "parse the JSON" in response.json()["error"]["message"]


def test_embeddings_shape_determinism_and_dimensions() -> None:
    body = post("/v1/embeddings", {"model": "text-embedding-3-small", "input": "hello"}).json()
    assert body["object"] == "list"
    vector = body["data"][0]["embedding"]
    assert len(vector) == 1536
    assert abs(sum(v * v for v in vector) - 1) < 1e-3
    assert body["usage"] == {
        "prompt_tokens": count_tokens("hello"),
        "total_tokens": count_tokens("hello"),
    }
    again = post("/v1/embeddings", {"model": "text-embedding-3-small", "input": "hello"}).json()
    assert again["data"][0]["embedding"] == vector

    large = post("/v1/embeddings", {"model": "text-embedding-3-large", "input": ["a", "b"]}).json()
    assert [len(d["embedding"]) for d in large["data"]] == [3072, 3072]
    assert large["data"][0]["embedding"] != large["data"][1]["embedding"]
    small = post("/v1/embeddings", {"model": "m", "input": "a", "dimensions": 8}).json()
    assert len(small["data"][0]["embedding"]) == 8


def test_embeddings_base64_and_token_array_input() -> None:
    body = post(
        "/v1/embeddings",
        {"model": "m", "input": [1, 2, 3], "dimensions": 4, "encoding_format": "base64"},
    ).json()
    raw = base64.b64decode(body["data"][0]["embedding"])
    assert len(struct.unpack("<4f", raw)) == 4
    assert body["usage"]["prompt_tokens"] == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"input": "x"},
        {"model": "m"},
        {"model": "m", "input": ""},
        {"model": "m", "input": []},
        {"model": "m", "input": [{"a": 1}]},
        {"model": "m", "input": ["x"] * 2049},
        {"model": "m", "input": "x", "dimensions": 0},
        {"model": "m", "input": "x", "encoding_format": "hex"},
    ],
)
def test_bad_embeddings_input(payload: dict[str, Any]) -> None:
    response = post("/v1/embeddings", payload)
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


def test_models_list() -> None:
    body = call("GET", "/v1/models").json()
    assert body["object"] == "list"
    ids = {m["id"] for m in body["data"]}
    assert {"gpt-4o", "gpt-4o-mini", "text-embedding-3-small"} <= ids
    assert all(m["object"] == "model" for m in body["data"])


def test_mock_never_echoes_request_headers_or_secrets() -> None:
    headers = {
        "Authorization": "Bearer sk-live-SECRET123",
        "X-Overcall-Key": "ocg_SECRET456",
        "X-Custom": "SECRET789",
        "Cookie": "session=SECRET000",
    }
    for response in (
        post("/v1/chat/completions", CHAT, headers),
        post("/v1/chat/completions", {**CHAT, "stream": True}, headers),
        post("/v1/embeddings", {"model": "m", "input": "x"}, headers),
        post("/v1/chat/completions", {"model": "m"}, headers),
        post("/v1/chat/completions", CHAT, {**headers, "X-Mock-Status": "500"}),
    ):
        haystack = response.text + str(dict(response.headers))
        assert "SECRET" not in haystack


def test_mock_does_not_echo_prompt_text() -> None:
    marker = "UNIQUE-PROMPT-MARKER-12345"
    payload = {**CHAT, "messages": [{"role": "user", "content": marker}]}
    assert marker not in post("/v1/chat/completions", payload).text


def test_mock_is_in_process_only() -> None:
    client = create_mock_client()
    assert isinstance(client._transport, StreamingASGITransport)
    assert str(client.base_url).startswith(MOCK_BASE_URL)
    asyncio.run(client.aclose())

    mock = create_mock_app()
    assert mock.openapi_url is None and mock.docs_url is None

    paths = {getattr(route, "path", "") for route in create_app().routes}
    assert not paths & {"/v1/chat/completions", "/v1/embeddings", "/v1/models"}
    assert not any("mock" in path or "completions" in path for path in paths)
