from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .tokens import (
    MAX_PAD_BYTES,
    count_message_tokens,
    count_tokens,
    embedding_vector,
    generate_text,
    request_seed,
    split_stream_pieces,
)
from .transport import StreamingASGITransport

MOCK_BASE_URL = "http://mock-openai.invalid"
MAX_BODY_BYTES = 8_000_000
MAX_LATENCY_MS = 10_000
MAX_CHOICES = 8
MAX_EMBEDDING_INPUTS = 2048
ALLOWED_MOCK_STATUS = {429, 500, 503}
ROLES = {"system", "developer", "user", "assistant", "tool", "function"}

MODELS = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-4o-mini",
    "gpt-4.1-mini",
    "text-embedding-3-small",
    "text-embedding-3-large",
)

INJECTED_ERRORS = {
    429: (
        "Rate limit reached for requests. Please try again later.",
        "requests",
        "rate_limit_exceeded",
    ),
    500: (
        "The server had an error while processing your request. Sorry about that!",
        "server_error",
        None,
    ),
    503: ("The engine is currently overloaded, please try again later.", "server_error", None),
}


class MockError(Exception):
    def __init__(
        self,
        status: int,
        message: str,
        *,
        kind: str = "invalid_request_error",
        param: str | None = None,
        code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = {"error": {"message": message, "type": kind, "param": param, "code": code}}
        self.headers = headers or {}


@dataclass(frozen=True)
class Injection:
    status: int | None = None
    latency_ms: int = 0
    retry_after: str | None = None
    drop_after_chunks: int | None = None
    resp_bytes: int | None = None


def _bounded_int(request: Request, name: str, low: int, high: int) -> int | None:
    raw = request.headers.get(name)
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        value = low - 1
    if not low <= value <= high:
        raise MockError(400, f"Invalid {name} header.", param=name.lower())
    return value


def read_injection(request: Request) -> Injection:
    status = _bounded_int(request, "X-Mock-Status", 100, 599)
    if status is not None and status not in ALLOWED_MOCK_STATUS:
        raise MockError(400, "Invalid X-Mock-Status header.", param="x-mock-status")
    retry_after = request.headers.get("X-Mock-Retry-After")
    if retry_after is not None and not retry_after.isdigit():
        raise MockError(400, "Invalid X-Mock-Retry-After header.", param="x-mock-retry-after")
    return Injection(
        status=status,
        latency_ms=_bounded_int(request, "X-Mock-Latency-Ms", 0, MAX_LATENCY_MS) or 0,
        retry_after=retry_after,
        drop_after_chunks=_bounded_int(request, "X-Mock-Drop-After-Chunks", 0, 10_000),
        resp_bytes=_bounded_int(request, "X-Mock-Resp-Bytes", 0, MAX_PAD_BYTES),
    )


async def _apply_failure(injection: Injection) -> None:
    if injection.latency_ms:
        await asyncio.sleep(injection.latency_ms / 1000)
    if injection.status is not None:
        message, kind, code = INJECTED_ERRORS[injection.status]
        headers = {"Retry-After": injection.retry_after} if injection.retry_after else {}
        raise MockError(injection.status, message, kind=kind, code=code, headers=headers)


async def _read_json(request: Request) -> dict[str, Any]:
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise MockError(413, "Request body is too large.", code="request_too_large")
    try:
        payload = json.loads(body)
    except ValueError:
        raise MockError(400, "We could not parse the JSON body of your request.") from None
    if not isinstance(payload, dict):
        raise MockError(400, "We could not parse the JSON body of your request.")
    return payload


def _require_model(payload: dict[str, Any]) -> str:
    model = payload.get("model")
    if model is None:
        raise MockError(400, "you must provide a model parameter.", param="model")
    if not isinstance(model, str) or not model.strip():
        raise MockError(400, "'model' must be a non-empty string.", param="model")
    return model


def _int_param(payload: dict[str, Any], name: str, low: int, high: int) -> int | None:
    value = payload.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise MockError(
            400, f"Invalid '{name}': expected an integer from {low} to {high}.", param=name
        )
    return value


def _validate_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "messages" not in payload:
        raise MockError(
            400,
            "Missing required parameter: 'messages'.",
            param="messages",
            code="missing_required_parameter",
        )
    messages = payload["messages"]
    if not isinstance(messages, list):
        raise MockError(400, "Invalid type for 'messages': expected an array.", param="messages")
    if not messages:
        raise MockError(
            400, "Invalid 'messages': empty array. Expected an array with minimum length 1.",
            param="messages",
        )  # fmt: skip
    for index, message in enumerate(messages):
        param = f"messages[{index}]"
        if not isinstance(message, dict) or message.get("role") not in ROLES:
            raise MockError(400, f"Invalid '{param}': a valid role is required.", param=param)
        if not isinstance(message.get("content"), str | list | type(None)):
            raise MockError(
                400, f"Invalid '{param}.content': expected a string or array.", param=param
            )
    return messages


def _padding(injection: Injection, current_bytes: int) -> str:
    if injection.resp_bytes is None or injection.resp_bytes <= current_bytes:
        return ""
    return "x" * (injection.resp_bytes - current_bytes)


def chat_completion(payload: dict[str, Any], injection: Injection) -> dict[str, Any]:
    model = _require_model(payload)
    messages = _validate_messages(payload)
    n = _int_param(payload, "n", 1, MAX_CHOICES) or 1
    max_tokens = _int_param(payload, "max_completion_tokens", 1, 128_000) or _int_param(
        payload, "max_tokens", 1, 128_000
    )
    seed = request_seed(payload)
    texts = [generate_text(seed, index, max_tokens) for index in range(n)]
    contents = [text for text, _ in texts]

    def build(parts: list[str]) -> dict[str, Any]:
        prompt = count_message_tokens(messages)
        completion = sum(count_tokens(part) for part in parts)
        return {
            "id": f"chatcmpl-{uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": index,
                    "message": {"role": "assistant", "content": part, "refusal": None},
                    "logprobs": None,
                    "finish_reason": texts[index][1],
                }
                for index, part in enumerate(parts)
            ],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            },
            "system_fingerprint": "fp_mock",
        }

    response = build(contents)
    for _ in range(3):
        rendered = len(json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode())
        padding = _padding(injection, rendered)
        if not padding:
            break
        contents[0] += padding
        response = build(contents)
    return response


def chat_stream_chunks(payload: dict[str, Any], injection: Injection) -> list[dict[str, Any]]:
    model = _require_model(payload)
    messages = _validate_messages(payload)
    options = payload.get("stream_options")
    if options is not None and not isinstance(options, dict):
        raise MockError(400, "Invalid 'stream_options'.", param="stream_options")
    include_usage = bool(options and options.get("include_usage") is True)
    n = _int_param(payload, "n", 1, MAX_CHOICES) or 1
    max_tokens = _int_param(payload, "max_completion_tokens", 1, 128_000) or _int_param(
        payload, "max_tokens", 1, 128_000
    )
    seed = request_seed(payload)
    texts = [generate_text(seed, index, max_tokens) for index in range(n)]
    contents = [text for text, _ in texts]
    if injection.resp_bytes:
        contents[0] += "x" * min(injection.resp_bytes, MAX_PAD_BYTES)

    chunk_id, created = f"chatcmpl-{uuid4().hex[:24]}", int(time.time())

    def chunk(choices: list[dict[str, Any]], usage: dict[str, int] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": "fp_mock",
            "choices": choices,
        }
        if include_usage:
            body["usage"] = usage
        return body

    def choice(index: int, delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
        return {"index": index, "delta": delta, "logprobs": None, "finish_reason": finish}

    chunks = [
        chunk([choice(i, {"role": "assistant", "content": "", "refusal": None}) for i in range(n)])
    ]
    pieces = [split_stream_pieces(content) for content in contents]
    for position in range(max(len(p) for p in pieces)):
        for index in range(n):
            if position < len(pieces[index]):
                chunks.append(chunk([choice(index, {"content": pieces[index][position]})]))
    for index in range(n):
        chunks.append(chunk([choice(index, {}, texts[index][1])]))
    if include_usage:
        prompt = count_message_tokens(messages)
        completion = sum(count_tokens(content) for content in contents)
        chunks.append(
            chunk(
                [],
                {
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "total_tokens": prompt + completion,
                },
            )
        )
    return chunks


async def _sse(chunks: list[dict[str, Any]], drop_after: int | None) -> AsyncIterator[bytes]:
    for sent, body in enumerate(chunks):
        if drop_after is not None and sent >= drop_after:
            return
        yield f"data: {json.dumps(body, separators=(',', ':'))}\n\n".encode()
    yield b"data: [DONE]\n\n"


def embeddings(payload: dict[str, Any], injection: Injection) -> dict[str, Any]:
    model = _require_model(payload)
    if "input" not in payload:
        raise MockError(
            400, "Missing required parameter: 'input'.", param="input",
            code="missing_required_parameter",
        )  # fmt: skip
    raw = payload["input"]
    items: list[Any] = [raw] if isinstance(raw, str) or _is_int_list(raw) else raw
    if not isinstance(items, list) or not items:
        raise MockError(400, "Invalid 'input': expected text or a non-empty array.", param="input")
    if len(items) > MAX_EMBEDDING_INPUTS:
        raise MockError(400, "Too many inputs.", param="input")
    tokens = 0
    for item in items:
        if isinstance(item, str):
            if not item:
                raise MockError(400, "Invalid 'input': empty string.", param="input")
            tokens += count_tokens(item)
        elif _is_int_list(item):
            tokens += len(item)
        else:
            raise MockError(400, "Invalid 'input' item.", param="input")
    default_dims = 3072 if model.endswith("large") else 1536
    dimensions = _int_param(payload, "dimensions", 1, 3072) or default_dims
    encoding = payload.get("encoding_format", "float")
    if encoding not in ("float", "base64"):
        raise MockError(400, "Invalid 'encoding_format'.", param="encoding_format")
    seed = request_seed(payload)
    data = []
    for index in range(len(items)):
        vector: Any = embedding_vector(seed, index, dimensions)
        if encoding == "base64":
            vector = base64.b64encode(struct.pack(f"<{len(vector)}f", *vector)).decode()
        data.append({"object": "embedding", "index": index, "embedding": vector})
    return {
        "object": "list",
        "data": data,
        "model": model,
        "usage": {"prompt_tokens": tokens, "total_tokens": tokens},
    }


def _is_int_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    )


def create_mock_app() -> FastAPI:
    app = FastAPI(title="Overcall mock OpenAI", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(MockError)
    async def mock_error_handler(_: Request, exc: MockError) -> JSONResponse:
        return JSONResponse(exc.body, status_code=exc.status, headers=exc.headers)

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        injection = read_injection(request)
        await _apply_failure(injection)
        payload = await _read_json(request)
        if payload.get("stream") is True:
            chunks = chat_stream_chunks(payload, injection)
            return StreamingResponse(
                _sse(chunks, injection.drop_after_chunks), media_type="text/event-stream"
            )
        if payload.get("stream_options") is not None:
            raise MockError(
                400,
                "The 'stream_options' parameter is only allowed when 'stream' is enabled.",
                param="stream_options",
            )
        return JSONResponse(chat_completion(payload, injection))

    @app.post("/v1/embeddings")
    async def create_embeddings(request: Request):
        injection = read_injection(request)
        await _apply_failure(injection)
        payload = await _read_json(request)
        return JSONResponse(embeddings(payload, injection))

    @app.get("/v1/models")
    async def list_models(request: Request):
        await _apply_failure(read_injection(request))
        return {
            "object": "list",
            "data": [
                {"id": model, "object": "model", "created": 1_700_000_000, "owned_by": "mock"}
                for model in MODELS
            ],
        }

    return app


def create_mock_client(base_url: str = MOCK_BASE_URL) -> httpx.AsyncClient:
    """An httpx client wired straight to the mock app. No socket is ever opened."""
    return httpx.AsyncClient(transport=StreamingASGITransport(create_mock_app()), base_url=base_url)
