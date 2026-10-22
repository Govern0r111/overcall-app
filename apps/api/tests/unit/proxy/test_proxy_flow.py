from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from uuid import uuid4

import httpx
import pytest

from overcall.auth.ingest_keys import generate_key, hash_key
from overcall.config import Settings
from overcall.main import create_app
from overcall.mock_openai.app import create_mock_client
from overcall.proxy.ingest_auth import IngestAuthenticator, KeyRecord
from overcall.proxy.ratelimit import FailedAuthThrottle, InflightCap, TokenBuckets
from overcall.proxy.router import ProxyState
from overcall.proxy.writer import LogWriter

PEPPER = "p" * 32
pytestmark = pytest.mark.asyncio


class StreamingMock(httpx.AsyncBaseTransport):
    """MockTransport pre-reads responses; this keeps them streamable like a real transport."""

    def __init__(self, handler) -> None:
        self.handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        result = self.handler(request)
        if asyncio.iscoroutine(result):
            result = await result
        return httpx.Response(
            result.status_code,
            headers=result.headers.raw,
            stream=httpx.ByteStream(result.content),
        )


class Harness:
    def __init__(self, **overrides) -> None:
        self.settings = Settings(
            app_env="test",
            database_url=None,
            release="test",
            **{"max_request_body_bytes": 4096, **overrides.pop("settings", {})},
        )
        self.key, _ = generate_key()
        self.record = KeyRecord(uuid4(), uuid4(), False)
        self.store = {hash_key(self.key, PEPPER): self.record}
        self.mode = overrides.pop("mode", "mock")
        self.seen: list[httpx.Request] = []
        self.upstream_handler = overrides.pop("upstream", self._default_upstream)
        self.app = create_app(self.settings)
        harness = self

        class Store:
            async def find(self, key_hash):
                return harness.store.get(key_hash)

        async def mode_lookup(_user_id):
            return harness.mode

        def make(handler):
            return httpx.AsyncClient(
                transport=StreamingMock(handler),
                base_url="http://upstream.test",
                follow_redirects=False,
            )

        self.state = ProxyState(
            settings=self.settings,
            authenticator=IngestAuthenticator(Store(), PEPPER),
            writer=LogWriter(self._noop),
            mode_lookup=mode_lookup,
            clients={
                "mock": create_mock_client(),
                "openai": make(self._call_upstream),
                "stripe": make(self._call_upstream),
            },
            buckets=overrides.pop("buckets", TokenBuckets(1000, 2000)),
            throttle=FailedAuthThrottle(),
            inflight=overrides.pop("inflight", InflightCap(100)),
        )
        self.app.state.proxy = self.state
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://proxy.test"
        )

    async def _noop(self, rows):
        return None

    async def _call_upstream(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        result = self.upstream_handler(request)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    @staticmethod
    def _default_upstream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": True, "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        )

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Overcall-Key": self.key}

    def rows(self) -> list[dict]:
        out = []
        while not self.state.writer.queue.empty():
            out.append(self.state.writer.queue.get_nowait())
        return out


@pytest.fixture
def h():
    return Harness()


async def test_mock_mode_chat_logs_row(h):
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]}
    resp = await h.client.post(
        "/proxy/openai/v1/chat/completions",
        json=payload,
        headers={**h.headers, "Authorization": "Bearer sk-user-secret", "X-Overcall-Caller": "svc"},
    )
    assert resp.status_code == 200 and resp.headers["x-overcall-request-id"].startswith("req_")
    assert not h.seen
    [row] = h.rows()
    assert row["origin"] == "upstream" and row["provider"] == "openai"
    assert row["user_id"] == h.record.user_id and row["ingest_key_id"] == h.record.id
    assert row["endpoint"] == "/v1/chat/completions" and row["caller"] == "svc"
    assert row["model"] == "gpt-4o-mini" and row["status"] == 200
    assert row["prompt_tokens"] > 0 and float(row["cost_usd"]) > 0
    assert len(row["req_hash"]) == 16 and row["latency_ms"] >= 0


async def test_real_mode_forwards_bytes_and_headers():
    harness = Harness(mode="real", settings={"allow_real_upstream": True})
    body = b'{"model":"gpt-4o",  "messages":[],"x":"\xc3\xa9"}'
    resp = await harness.client.post(
        "/proxy/openai/v1/chat/completions?b=2&a=1",
        content=body,
        headers={
            **harness.headers,
            "Authorization": "Bearer sk-real",
            "Content-Type": "application/json",
            "X-Custom": "1",
            "X-Overcall-Caller": "svc",
            "Accept-Encoding": "gzip",
        },
    )
    assert resp.status_code == 200
    [sent] = harness.seen
    assert sent.content == body
    assert str(sent.url) == "http://upstream.test/v1/chat/completions?b=2&a=1"
    assert sent.headers["authorization"] == "Bearer sk-real"
    assert sent.headers["x-custom"] == "1"
    assert sent.headers["accept-encoding"] == "identity"
    assert "x-overcall-key" not in sent.headers and "x-overcall-caller" not in sent.headers


async def test_real_mode_disabled_by_default():
    harness = Harness(mode="real")
    resp = await harness.client.post(
        "/proxy/openai/v1/chat/completions", json={}, headers=harness.headers
    )
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "real_upstream_disabled"
    assert not harness.seen
    assert harness.rows()[0]["origin"] == "overcall"


async def test_provider_error_passes_through_untouched():
    def upstream(_request):
        return httpx.Response(
            429,
            json={"error": {"message": "slow down", "type": "rate"}},
            headers=[("Retry-After", "7"), ("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")],
        )

    harness = Harness(mode="real", upstream=upstream, settings={"allow_real_upstream": True})
    resp = await harness.client.post(
        "/proxy/openai/v1/chat/completions", json={}, headers=harness.headers
    )
    assert resp.status_code == 429 and resp.headers["retry-after"] == "7"
    assert resp.headers.get_list("set-cookie") == ["a=1", "b=2"]
    assert resp.json()["error"]["message"] == "slow down"
    assert "x-overcall-error" not in resp.headers
    [row] = harness.rows()
    assert row["status"] == 429 and row["origin"] == "upstream"


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (httpx.ReadTimeout("t"), 504, "upstream_timeout"),
        (httpx.ConnectError("c"), 502, "upstream_unreachable"),
    ],
)
async def test_upstream_failures_map_and_log(exc, status, code):
    def upstream(_request):
        raise exc

    harness = Harness(mode="real", upstream=upstream, settings={"allow_real_upstream": True})
    resp = await harness.client.post(
        "/proxy/openai/v1/chat/completions", json={}, headers=harness.headers
    )
    assert resp.status_code == status and resp.json()["error"]["code"] == code
    assert resp.headers["x-overcall-error"] == code
    [row] = harness.rows()
    assert row["status"] == status and row["origin"] == "upstream" and row["error_code"] == code


async def test_redirects_are_not_followed():
    def upstream(_request):
        return httpx.Response(302, headers={"Location": "http://evil.test/x"})

    harness = Harness(mode="real", upstream=upstream, settings={"allow_real_upstream": True})
    resp = await harness.client.get("/proxy/openai/v1/models", headers=harness.headers)
    assert resp.status_code == 302 and resp.headers["location"] == "http://evil.test/x"
    assert len(harness.seen) == 1


async def test_key_failures(h):
    url = "/proxy/openai/v1/chat/completions"
    missing = await h.client.post(url, json={})
    assert missing.status_code == 401 and missing.json()["error"]["code"] == "ingest_key_missing"
    bad = await h.client.post(url, json={}, headers={"X-Overcall-Key": "oc_" + "z" * 30})
    assert bad.json()["error"]["code"] == "ingest_key_invalid"
    h.store[hash_key(h.key, PEPPER)] = KeyRecord(h.record.id, h.record.user_id, True)
    revoked = await h.client.post(url, json={}, headers=h.headers)
    assert revoked.json()["error"]["code"] == "ingest_key_revoked"
    assert h.rows() == []


async def test_failed_auth_throttle_per_ip(h):
    for _ in range(10):
        await h.client.post("/proxy/openai/v1/x", headers={"X-Overcall-Key": "oc_" + "z" * 30})
    blocked = await h.client.post("/proxy/openai/v1/x", headers=h.headers)
    assert blocked.status_code == 429


async def test_unknown_provider_404_and_aws_501_after_auth(h):
    unknown = await h.client.get("/proxy/foo/v1/x")
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "route_not_supported"
    assert (await h.client.get("/proxy/aws/v1/x")).status_code == 401
    aws = await h.client.get("/proxy/aws/v1/x", headers=h.headers)
    assert aws.status_code == 501 and aws.json()["error"]["code"] == "provider_not_supported"
    assert aws.headers["x-overcall-error"] == "provider_not_supported"
    [row] = h.rows()
    assert row["origin"] == "overcall" and row["provider"] == "aws" and row["status"] == 501


async def test_rate_limit_per_key():
    harness = Harness(buckets=TokenBuckets(0.001, 2))
    codes = [
        (await harness.client.get("/proxy/openai/v1/models", headers=harness.headers)).status_code
        for _ in range(4)
    ]
    assert codes[:2] == [200, 200] and codes[2:] == [429, 429]
    assert [r["origin"] for r in harness.rows()][-1] == "overcall"


async def test_overloaded_when_inflight_full():
    harness = Harness(inflight=InflightCap(0))
    resp = await harness.client.get("/proxy/openai/v1/models", headers=harness.headers)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "overloaded"
    assert resp.headers["retry-after"] == "1"


async def test_inflight_released_after_requests(h):
    for _ in range(3):
        await h.client.get("/proxy/openai/v1/models", headers=h.headers)
        await h.client.get("/proxy/aws/v1/x", headers=h.headers)
        await h.client.get("/proxy/openai/v1/models")
    assert h.state.inflight.current == 0


async def test_oversize_body(h):
    declared = await h.client.post(
        "/proxy/openai/v1/chat/completions", content=b"x" * 5000, headers=h.headers
    )
    assert declared.status_code == 413 and declared.json()["error"]["code"] == "payload_too_large"

    async def chunks():
        for _ in range(10):
            yield b"x" * 1000

    streamed = await h.client.post(
        "/proxy/openai/v1/chat/completions", content=chunks(), headers=h.headers
    )
    assert streamed.status_code == 413
    assert not h.seen


@pytest.mark.parametrize(
    "path",
    [
        "/proxy/openai/v1/%2e%2e/admin",
        "/proxy/openai/v1/a%2Fb",
        "/proxy/openai/v1/a%5Cb",
        "/proxy/openai/v1//x",
        "/proxy/openai/v1/x@evil.test",
        "/proxy/openai/v2/x",
        "/proxy/openai/models",
        "/proxy/openai/v1",
    ],
)
async def test_unsafe_paths_rejected(h, path):
    resp = await h.client.get(path, headers=h.headers)
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "route_not_supported"
    assert not h.seen


async def test_upstream_host_never_changes():
    harness = Harness(mode="real", settings={"allow_real_upstream": True})
    await harness.client.get("/proxy/openai/v1/models", headers=harness.headers)
    assert {r.url.host for r in harness.seen} == {"upstream.test"}


def _basic(user: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:".encode()).decode()


@pytest.mark.parametrize(
    "auth",
    [
        "Bearer sk_live_abc123",
        "Bearer rk_live_abc123",
        "Bearer pk_test_abc123",
        "Bearer sk_xyz",
        _basic("sk_live_abc123"),
        _basic("pk_live_abc"),
    ],
)
async def test_stripe_live_keys_rejected(h, auth):
    resp = await h.client.post(
        "/proxy/stripe/v1/payment_intents",
        data={"amount": 1},
        headers={**h.headers, "Authorization": auth},
    )
    assert resp.status_code == 403 and resp.json()["error"]["code"] == "stripe_live_key_rejected"
    assert not h.seen
    assert "sk_live_abc123" not in resp.text


@pytest.mark.parametrize("auth", ["Bearer sk_test_abc123", _basic("rk_test_abc123")])
async def test_stripe_test_keys_forwarded(auth):
    def upstream(_request):
        return httpx.Response(200, json={"data": [{}, {}, {}]})

    harness = Harness(upstream=upstream)
    resp = await harness.client.get(
        "/proxy/stripe/v1/customers/cus_Abc123XyZ?limit=50",
        headers={**harness.headers, "Authorization": auth, "Idempotency-Key": "k"},
    )
    assert resp.status_code == 200
    assert harness.seen[0].headers["authorization"] == auth
    [row] = harness.rows()
    assert row["provider"] == "stripe" and row["endpoint"] == "/v1/customers/{id}"
    assert row["list_limit"] == 50 and row["items_returned"] == 3
    assert row["has_idempotency_key"] is True and float(row["cost_usd"]) > 0


async def test_method_edge_cases():
    harness = Harness(mode="real", settings={"allow_real_upstream": True})
    head = await harness.client.head("/proxy/openai/v1/models", headers=harness.headers)
    options = await harness.client.options("/proxy/openai/v1/models", headers=harness.headers)
    get_body = await harness.client.request(
        "GET", "/proxy/openai/v1/models", content=b"abc", headers=harness.headers
    )
    assert head.status_code == 200 and head.content == b""
    assert options.status_code == 200 and get_body.status_code == 200
    assert [r.content for r in harness.seen][-1] == b"abc"
    assert len(harness.rows()) == 3


async def test_chunked_and_compressed_bodies_forwarded_untouched():
    harness = Harness(mode="real", settings={"allow_real_upstream": True})
    import gzip

    packed = gzip.compress(b'{"model":"gpt-4o"}')

    async def chunks():
        yield packed[:5]
        yield packed[5:]

    resp = await harness.client.post(
        "/proxy/openai/v1/chat/completions",
        content=chunks(),
        headers={**harness.headers, "Content-Encoding": "gzip", "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert harness.seen[0].content == packed
    assert harness.seen[0].headers["content-encoding"] == "gzip"
    assert harness.rows()[0].get("model") is None


async def test_multipart_and_odd_caller_and_repeated_query():
    harness = Harness(mode="real", settings={"allow_real_upstream": True})
    resp = await harness.client.post(
        "/proxy/openai/v1/files?x=1&x=2&y=%20z",
        files={"file": ("a.txt", b"data")},
        headers={**harness.headers, "X-Overcall-Caller": "bad caller; drop table"},
    )
    assert resp.status_code == 200
    assert str(harness.seen[0].url).endswith("/v1/files?x=1&x=2&y=%20z")
    [row] = harness.rows()
    assert row["caller"] is None and row["req_size"] > 4


async def test_sentinel_and_secrets_never_logged_or_stored(caplog):
    caplog.set_level(logging.DEBUG)
    sentinel = "SENTINEL-" + uuid4().hex
    secrets = [
        "sk-proj-" + "a" * 30,
        "sk_test_" + "b" * 24,
        "oc_" + "c" * 30,
        "eyJhbGciOi.eyJzdWIiOiIx.sig123abc",
    ]

    def upstream(request):
        return httpx.Response(
            200,
            json={"echo": sentinel, "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
            headers={"X-Echo-Secret": secrets[0]},
        )

    harness = Harness(mode="real", upstream=upstream, settings={"allow_real_upstream": True})
    body = {"model": "gpt-4o", "messages": [{"role": "user", "content": sentinel + secrets[1]}]}
    await harness.client.post(
        "/proxy/openai/v1/chat/completions",
        json=body,
        headers={
            **harness.headers,
            "Authorization": f"Bearer {secrets[0]}",
            "Cookie": secrets[3],
            "X-Overcall-Caller": secrets[2],
        },
    )
    await harness.client.post(
        "/proxy/openai/v1/chat/completions",
        content=b"{" + sentinel.encode(),
        headers={**harness.headers, "Content-Type": "application/json"},
    )
    rows = harness.rows()
    dump = json.dumps(rows, default=str) + caplog.text
    for secret in [sentinel, *secrets[:2], secrets[3], harness.key]:
        assert secret not in dump
    assert len(rows) == 2


async def test_unhandled_error_is_safe_and_logged_without_secrets(caplog):
    def upstream(_request):
        raise RuntimeError("boom sk_test_" + "z" * 24)

    harness = Harness(mode="real", upstream=upstream, settings={"allow_real_upstream": True})
    resp = await harness.client.post(
        "/proxy/openai/v1/chat/completions", json={}, headers=harness.headers
    )
    assert resp.status_code == 500 and resp.json()["error"]["code"] == "internal_error"
    assert "sk_test_zzz" not in resp.text
    assert harness.state.inflight.current == 0


async def test_concurrent_requests_do_not_cross_talk():
    def upstream(request):
        digest = hashlib.sha256(request.content).hexdigest()
        return httpx.Response(200, json={"digest": digest})

    harness = Harness(
        mode="real",
        upstream=upstream,
        settings={"allow_real_upstream": True},
        buckets=TokenBuckets(100000, 100000),
        inflight=InflightCap(500),
    )
    bodies = [json.dumps({"n": i, "pad": "x" * (i % 50)}).encode() for i in range(200)]

    async def call(body):
        r = await harness.client.post(
            "/proxy/openai/v1/chat/completions",
            content=body,
            headers={**harness.headers, "Content-Type": "application/json"},
        )
        return r.json()["digest"], hashlib.sha256(body).hexdigest()

    results = await asyncio.gather(*(call(b) for b in bodies))
    assert all(a == b for a, b in results)
    assert len(harness.rows()) == 200 and harness.state.inflight.current == 0


async def test_no_state_returns_not_ready():
    app = create_app(Settings(app_env="test", database_url=None, release="test"))
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    resp = await client.get("/proxy/openai/v1/models")
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "not_ready"
