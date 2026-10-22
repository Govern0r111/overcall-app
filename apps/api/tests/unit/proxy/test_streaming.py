from __future__ import annotations

import asyncio
import json
import time
from uuid import uuid4

import httpx
import pytest

from overcall.auth.ingest_keys import generate_key, hash_key
from overcall.config import Settings
from overcall.main import create_app
from overcall.mock_openai.app import create_mock_client
from overcall.mock_openai.transport import StreamingASGITransport
from overcall.proxy.ingest_auth import IngestAuthenticator, KeyRecord
from overcall.proxy.ratelimit import FailedAuthThrottle, InflightCap, TokenBuckets
from overcall.proxy.router import ProxyState
from overcall.proxy.writer import LogWriter

PEPPER = "p" * 32
URL = "/proxy/openai/v1/chat/completions"
pytestmark = pytest.mark.asyncio


class GenStream(httpx.AsyncByteStream):
    def __init__(self, agen, on_close) -> None:
        self.agen = agen
        self.on_close = on_close

    async def __aiter__(self):
        async for chunk in self.agen:
            yield chunk

    async def aclose(self) -> None:
        self.on_close()
        await self.agen.aclose()


class GenTransport(httpx.AsyncBaseTransport):
    def __init__(self, factory) -> None:
        self.factory = factory
        self.closed = False

    async def handle_async_request(self, request):
        await request.aread()
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=GenStream(self.factory(), lambda: setattr(self, "closed", True)),
        )


def sse(obj) -> bytes:
    return b"data: " + (obj if isinstance(obj, bytes) else json.dumps(obj).encode()) + b"\n\n"


class Rig:
    def __init__(self, upstream: GenTransport | None = None) -> None:
        settings = Settings(app_env="test", database_url=None, release="test")
        self.key, _ = generate_key()
        record = KeyRecord(uuid4(), uuid4(), False)
        store = {hash_key(self.key, PEPPER): record}

        class Store:
            async def find(self, key_hash):
                return store.get(key_hash)

        async def mode(_user):
            return "mock"

        mock = create_mock_client()
        if upstream is not None:
            mock = httpx.AsyncClient(transport=upstream, base_url="http://mock-openai.invalid")
        self.state = ProxyState(
            settings=settings,
            authenticator=IngestAuthenticator(Store(), PEPPER),
            writer=LogWriter(self._sink),
            mode_lookup=mode,
            clients={"mock": mock, "openai": mock, "stripe": mock},
            buckets=TokenBuckets(1000, 2000),
            throttle=FailedAuthThrottle(),
            inflight=InflightCap(100),
        )
        app = create_app(settings)
        app.state.proxy = self.state
        self.client = httpx.AsyncClient(
            transport=StreamingASGITransport(app), base_url="http://proxy.test"
        )

    async def _sink(self, rows):
        return None

    @property
    def headers(self):
        return {"X-Overcall-Key": self.key}

    async def row(self, timeout: float = 3.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.state.writer.queue.empty():
                return self.state.writer.queue.get_nowait()
            await asyncio.sleep(0.01)
        raise AssertionError("no log row written")


CHAT = {"model": "gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": "hi"}]}


async def test_usage_chunk_gives_billed_cost():
    rig = Rig()
    body = {**CHAT, "stream_options": {"include_usage": True}}
    resp = await rig.client.post(URL, json=body, headers=rig.headers)
    assert resp.status_code == 200 and "text/event-stream" in resp.headers["content-type"]
    assert resp.content.rstrip().endswith(b"data: [DONE]")
    row = await rig.row()
    assert row["stream"] is True and row["tokens_estimated"] is False
    assert row["cost_basis"] == "billed" and row["prompt_tokens"] > 0
    assert row["completion_tokens"] > 0 and row["error_code"] is None
    assert row["ttfb_ms"] is not None and row["latency_ms"] >= row["ttfb_ms"]


async def test_missing_usage_is_estimated_and_labelled():
    rig = Rig()
    resp = await rig.client.post(URL, json=CHAT, headers=rig.headers)
    assert resp.status_code == 200
    row = await rig.row()
    assert row["stream"] is True and row["tokens_estimated"] is True
    assert row["cost_basis"] == "estimated" and row["completion_tokens"] > 0
    assert row["prompt_tokens"] > 0 and float(row["cost_usd"]) > 0


async def test_mock_drop_is_logged_as_upstream_dropped():
    rig = Rig()
    resp = await rig.client.post(
        URL, json=CHAT, headers={**rig.headers, "X-Mock-Drop-After-Chunks": "2"}
    )
    assert b"[DONE]" not in resp.content
    row = await rig.row()
    assert row["error_code"] == "upstream_dropped" and row["tokens_estimated"] is True
    assert rig.state.inflight.current == 0


async def test_first_chunk_arrives_before_stream_finishes():
    gate = asyncio.Event()

    async def upstream():
        yield sse({"choices": [{"delta": {"content": "first"}}]})
        await gate.wait()
        yield sse({"choices": [{"delta": {"content": "second"}}]})
        yield sse(b"[DONE]")

    transport = GenTransport(upstream)
    rig = Rig(transport)
    async with rig.client.stream("POST", URL, json=CHAT, headers=rig.headers) as response:
        iterator = response.aiter_raw()
        first = await asyncio.wait_for(iterator.__anext__(), timeout=2)
        assert b"first" in first and not gate.is_set()
        gate.set()
        rest = b"".join([chunk async for chunk in iterator])
    assert b"second" in rest and rest.rstrip().endswith(b"[DONE]")
    row = await rig.row()
    assert row["ttfb_ms"] < row["latency_ms"] and row["error_code"] is None
    assert transport.closed and rig.state.inflight.current == 0


async def test_client_disconnect_closes_upstream_and_still_logs():
    async def upstream():
        for index in range(1000):
            yield sse({"choices": [{"delta": {"content": f"piece{index}"}}]})
            await asyncio.sleep(0.01)

    transport = GenTransport(upstream)
    rig = Rig(transport)
    async with rig.client.stream("POST", URL, json=CHAT, headers=rig.headers) as response:
        async for _ in response.aiter_raw():
            break
    row = await rig.row()
    assert row["error_code"] == "client_disconnected" and row["stream"] is True
    assert transport.closed and rig.state.inflight.current == 0
    assert row["tokens_estimated"] is True


async def test_error_event_midstream_is_flagged_and_passed_through():
    async def upstream():
        yield sse({"choices": [{"delta": {"content": "ok"}}]})
        yield b'event: error\ndata: {"error":{"message":"overloaded"}}\n\n'
        yield sse(b"[DONE]")

    rig = Rig(GenTransport(upstream))
    resp = await rig.client.post(URL, json=CHAT, headers=rig.headers)
    assert b"overloaded" in resp.content
    assert (await rig.row())["error_code"] == "stream_error"


async def test_missing_done_and_keepalive_and_unicode_split():
    text = "héllo ✓"

    async def upstream():
        yield b": keep-alive\n\n"
        payload = {"choices": [{"delta": {"content": text}}]}
        raw = b"data: " + json.dumps(payload, ensure_ascii=False).encode() + b"\n\n"
        yield raw[:12]
        yield raw[12:36]
        yield raw[36:]

    rig = Rig(GenTransport(upstream))
    resp = await rig.client.post(URL, json=CHAT, headers=rig.headers)
    assert text.encode() in resp.content
    row = await rig.row()
    assert row["error_code"] == "upstream_dropped" and row["completion_tokens"] == 2


async def test_no_stream_text_is_stored_or_logged(caplog):
    marker = "SENTINEL-" + uuid4().hex

    async def upstream():
        yield sse({"choices": [{"delta": {"content": marker}}]})
        yield sse(b"[DONE]")

    rig = Rig(GenTransport(upstream))
    body = {**CHAT, "messages": [{"role": "user", "content": marker}]}
    resp = await rig.client.post(URL, json=body, headers=rig.headers)
    assert marker.encode() in resp.content
    row = await rig.row()
    assert marker not in json.dumps(row, default=str) and marker not in caplog.text


async def test_slow_client_gets_bounded_progress_without_losing_data():
    big = "x" * 2000

    async def upstream():
        for _ in range(200):
            yield sse({"choices": [{"delta": {"content": big}}]})
        yield sse(b"[DONE]")

    rig = Rig(GenTransport(upstream))
    total = 0
    async with rig.client.stream("POST", URL, json=CHAT, headers=rig.headers) as response:
        async for chunk in response.aiter_raw():
            total += len(chunk)
            await asyncio.sleep(0)
    assert total > 200 * 2000
    assert (await rig.row())["resp_size"] == total
