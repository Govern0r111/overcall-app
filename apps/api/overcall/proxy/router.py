from __future__ import annotations

import asyncio
import base64
import re
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

import anyio
import httpx
from fastapi import APIRouter, Request
from starlette.responses import Response, StreamingResponse

from ..config import Settings
from ..errors import OvercallError
from ..logging import get_logger, get_request_id
from ..mock_openai.app import MOCK_BASE_URL, create_mock_client
from ..pricing import Usage, estimate_cost
from .errors import err, error_response
from .extract import (
    MAX_PARSE_BYTES,
    extract_openai_request,
    extract_openai_response,
    extract_stripe,
)
from .hashing import clean_caller, normalize_endpoint, request_hash
from .headers import client_response_headers, upstream_request_headers
from .ingest_auth import IngestAuthenticator, KeyRecord
from .ratelimit import FailedAuthThrottle, InflightCap, TokenBuckets
from .tokens import StreamTap, estimate_prompt_tokens, estimate_text_tokens
from .writer import LogWriter

logger = get_logger(__name__)
router = APIRouter()

PROVIDERS = {"openai", "stripe", "aws"}
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
_BAD_PATH = re.compile(r"(\.\.|//|\\|@|%2e|%2f|%5c|%00)", re.I)
_TEST_KEY = re.compile(r"^(sk|rk)_test_")
UPSTREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
UPSTREAM_LIMITS = httpx.Limits(
    max_connections=100, max_keepalive_connections=20, keepalive_expiry=30.0
)

ModeLookup = Callable[[UUID], Awaitable[str]]


@dataclass
class ProxyState:
    settings: Settings
    authenticator: IngestAuthenticator
    writer: LogWriter
    mode_lookup: ModeLookup
    clients: dict[str, httpx.AsyncClient]
    buckets: TokenBuckets
    throttle: FailedAuthThrottle
    inflight: InflightCap
    mode_ttl: float = 30.0
    _modes: OrderedDict[UUID, tuple[float, str]] = field(default_factory=OrderedDict)

    async def mode(self, user_id: UUID) -> str:
        now = time.monotonic()
        hit = self._modes.get(user_id)
        if hit and hit[0] > now:
            return hit[1]
        mode = await self.mode_lookup(user_id)
        self._modes[user_id] = (now + self.mode_ttl, mode)
        while len(self._modes) > 10_000:
            self._modes.popitem(last=False)
        return mode

    async def aclose(self) -> None:
        for client in self.clients.values():
            await client.aclose()


def build_clients(settings: Settings) -> dict[str, httpx.AsyncClient]:
    def real(base: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base,
            follow_redirects=False,
            http2=False,
            timeout=UPSTREAM_TIMEOUT,
            limits=UPSTREAM_LIMITS,
        )

    return {
        "mock": create_mock_client(),
        "openai": real(settings.openai_upstream_base_url),
        "stripe": real(settings.stripe_upstream_base_url),
    }


def _stripe_credential(headers: list[tuple[str, str]]) -> str | None:
    for name, value in headers:
        if name.lower() != "authorization":
            continue
        scheme, _, rest = value.partition(" ")
        rest = rest.strip()
        if scheme.lower() == "bearer":
            return rest
        if scheme.lower() == "basic":
            try:
                return base64.b64decode(rest, validate=False).decode().split(":", 1)[0]
            except ValueError:
                return ""
    return None


def _overcall_row(
    record: KeyRecord,
    provider: str,
    method: str,
    endpoint: str,
    code: str,
    status: int,
    received: datetime,
) -> dict[str, Any]:
    cost = estimate_cost(provider, None, None, status, received)
    return {
        "user_id": record.user_id,
        "ingest_key_id": record.id,
        "source": "proxy",
        "origin": "overcall",
        "occurred_at": received,
        "provider": provider,
        "method": method,
        "endpoint": endpoint[:256],
        "status": status,
        "latency_ms": 0,
        "req_size": 0,
        "resp_size": 0,
        "req_hash": "0" * 16,
        "tokens_estimated": False,
        "stream": False,
        "uses_tools": False,
        "has_idempotency_key": False,
        "cost_usd": 0,
        "cost_basis": "modelled",
        "pricing_version": cost.pricing_version,
        "error_code": code,
    }


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.api_route("/proxy/{provider}/{path:path}", methods=METHODS, include_in_schema=False)
async def proxy(request: Request, provider: str, path: str) -> Response:
    state: ProxyState | None = getattr(request.app.state, "proxy", None)
    if state is None:
        return error_response(err("not_ready"))
    if not state.inflight.acquire():
        return error_response(err("overloaded"), retry_after=1)
    released = False

    def release() -> None:
        nonlocal released
        if not released:
            released = True
            state.inflight.release()

    try:
        response = await _handle(request, state, provider, release)
    except OvercallError as exc:
        release()
        return error_response(exc)
    except BaseException:
        release()
        raise
    if not isinstance(response, StreamingResponse):
        release()
    return response


async def _handle(
    request: Request, state: ProxyState, provider: str, release: Callable[[], None]
) -> Response:
    settings = state.settings
    if provider not in PROVIDERS:
        raise err("route_not_supported")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_request_body_bytes:
        raise err("payload_too_large")

    ip = _client_ip(request)
    if state.throttle.blocked(ip):
        raise err("rate_limited")
    try:
        record = await state.authenticator.authenticate(request.headers.get("x-overcall-key"))
    except OvercallError as exc:
        if exc.code.startswith("ingest_key"):
            state.throttle.record_failure(ip)
        raise

    received = datetime.now(UTC)
    method = request.method.upper()
    raw = request.scope.get("raw_path") or request.scope["path"].encode()
    raw_path = raw.decode("latin-1")[len(f"/proxy/{provider}") :]
    endpoint = normalize_endpoint(request.scope["path"][len(f"/proxy/{provider}") :])

    def refuse(code: str) -> OvercallError:
        exc = err(code)
        state.writer.submit(
            _overcall_row(record, provider, method, endpoint, code, exc.status, received)
        )
        return exc

    if not state.buckets.allow(str(record.id)):
        raise refuse("rate_limited")
    if provider == "aws":
        raise refuse("provider_not_supported")
    if not raw_path.startswith("/v1/") or _BAD_PATH.search(raw_path):
        raise refuse("route_not_supported")

    raw_headers = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in request.scope["headers"]]
    if provider == "stripe":
        credential = _stripe_credential(raw_headers)
        if credential is not None and not _TEST_KEY.match(credential):
            raise refuse("stripe_live_key_rejected")

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > settings.max_request_body_bytes:
            raise refuse("payload_too_large")
        chunks.append(chunk)
    body = b"".join(chunks)

    mode = "test"
    if provider == "openai":
        mode = await state.mode(record.user_id)
        if mode == "real" and not settings.allow_real_upstream:
            raise refuse("real_upstream_disabled")
    use_mock = provider == "openai" and mode != "real"
    client = state.clients["mock" if use_mock else provider]
    base = MOCK_BASE_URL if use_mock else str(client.base_url).rstrip("/")
    query = request.scope.get("query_string", b"").decode("latin-1")
    url = base + raw_path + (f"?{query}" if query else "")
    if urlsplit(url).netloc != urlsplit(base).netloc:
        raise refuse("route_not_supported")

    out_headers = upstream_request_headers(raw_headers, drop_authorization=use_mock)
    content_type = request.headers.get("content-type")
    idem = request.headers.get("idempotency-key") is not None
    caller = clean_caller(request.headers.get("x-overcall-caller"))
    request_id = get_request_id()
    req_hash = request_hash(method, raw_path, query, body, content_type or "")
    if provider == "openai":
        req_fields = extract_openai_request(body, content_type)
    else:
        req_fields = extract_stripe(dict(parse_qsl(query)), b"", None)

    started = time.perf_counter()
    base_row: dict[str, Any] = {
        "user_id": record.user_id,
        "ingest_key_id": record.id,
        "source": "proxy",
        "occurred_at": received,
        "provider": provider,
        "method": method,
        "endpoint": endpoint[:256],
        "req_size": len(body),
        "req_hash": req_hash,
        "has_idempotency_key": idem,
        "caller": caller,
        "stream": False,
        "uses_tools": False,
        **req_fields,
    }

    def finish(
        status: int,
        resp_size: int,
        ttfb: float | None,
        resp_body: bytes,
        ctype: str | None,
        error_code: str | None = None,
        tap: StreamTap | None = None,
    ) -> None:
        try:
            row = dict(base_row)
            resp_fields: dict[str, Any] = {}
            estimated = False
            if tap is not None:
                row["stream"] = True
                if tap.model and not row.get("model"):
                    row["model"] = tap.model
                if tap.usage is not None:
                    resp_fields = dict(tap.usage)
                elif provider == "openai":
                    resp_fields = {
                        "prompt_tokens": estimate_prompt_tokens(body, content_type),
                        "completion_tokens": estimate_text_tokens(tap.text_chars),
                    }
                    estimated = True
            elif provider == "openai":
                resp_fields = extract_openai_response(resp_body, ctype)
            elif provider == "stripe":
                resp_fields = extract_stripe(dict(parse_qsl(query)), resp_body, ctype)
            row.update(resp_fields)
            usage = None
            if "prompt_tokens" in resp_fields or "completion_tokens" in resp_fields:
                usage = Usage(
                    prompt_tokens=resp_fields.get("prompt_tokens", 0),
                    completion_tokens=resp_fields.get("completion_tokens", 0),
                    cached_prompt_tokens=resp_fields.get("cached_prompt_tokens", 0),
                    tokens_estimated=estimated,
                )
            cost = estimate_cost(provider, row.get("model"), usage, status, received)
            row.update(
                origin="upstream",
                status=status,
                latency_ms=(time.perf_counter() - started) * 1000,
                ttfb_ms=ttfb,
                resp_size=resp_size,
                cost_usd=cost.cost_usd,
                cost_basis=cost.basis,
                pricing_version=cost.pricing_version,
                error_code=error_code,
                tokens_estimated=estimated,
            )
            state.writer.submit(row)
        except Exception:
            logger.error("log_row_build_failed provider=%s", provider)

    try:
        upstream_request = client.build_request(
            method, url, headers=out_headers, content=body if body else None
        )
        upstream = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        finish(504, 0, None, b"", None, "upstream_timeout")
        raise err("upstream_timeout") from None
    except httpx.HTTPError:
        finish(502, 0, None, b"", None, "upstream_unreachable")
        raise err("upstream_unreachable") from None

    headers_ms = (time.perf_counter() - started) * 1000
    ctype = upstream.headers.get("content-type")
    parse_cap = min(MAX_PARSE_BYTES, settings.max_response_buffer_bytes)
    is_json = bool(ctype and "json" in ctype.lower())
    is_sse = bool(ctype and ctype.split(";")[0].strip().lower() == "text/event-stream")
    chat_stream = provider == "openai" and is_sse and endpoint.endswith("/chat/completions")

    async def body_iter() -> AsyncIterator[bytes]:
        total = 0
        buffered: list[bytes] | None = [] if is_json else None
        tap = StreamTap() if is_sse and provider == "openai" else None
        error_code: str | None = None
        ttfb: float | None = None
        try:
            async for chunk in upstream.aiter_raw():
                total += len(chunk)
                if tap is not None:
                    tap.feed(chunk)
                elif buffered is not None:
                    if total > parse_cap:
                        buffered = None
                    else:
                        buffered.append(chunk)
                if ttfb is None:
                    ttfb = (time.perf_counter() - started) * 1000
                yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            error_code = "client_disconnected"
            raise
        except httpx.HTTPError:
            error_code = "upstream_dropped"
        finally:
            with anyio.CancelScope(shield=True):
                await upstream.aclose()
            if tap is not None:
                tap.finish()
                if error_code is None and tap.error_event:
                    error_code = "stream_error"
                elif error_code is None and chat_stream and not tap.done:
                    error_code = "upstream_dropped"
            finish(
                upstream.status_code,
                total,
                ttfb if ttfb is not None else headers_ms,
                b"".join(buffered) if buffered is not None else b"",
                ctype,
                error_code,
                tap,
            )
            release()

    headers = client_response_headers(list(upstream.headers.multi_items()), request_id)
    raw_headers_out = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers]
    if method == "HEAD":
        await upstream.aclose()
        finish(upstream.status_code, 0, headers_ms, b"", ctype)
        head = Response(status_code=upstream.status_code)
        head.raw_headers = raw_headers_out
        return head
    response = StreamingResponse(body_iter(), status_code=upstream.status_code)
    response.raw_headers = raw_headers_out
    return response
