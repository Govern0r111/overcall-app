from __future__ import annotations

import asyncio
import hashlib
import json
from uuid import uuid4

import pytest

from overcall.auth.ingest_keys import generate_key, hash_key, looks_like_key
from overcall.errors import OvercallError
from overcall.proxy.extract import (
    extract_openai_request,
    extract_openai_response,
    extract_stripe,
)
from overcall.proxy.hashing import clean_caller, normalize_endpoint, request_hash
from overcall.proxy.headers import client_response_headers, upstream_request_headers
from overcall.proxy.ingest_auth import IngestAuthenticator, KeyRecord
from overcall.proxy.ratelimit import FailedAuthThrottle, InflightCap, TokenBuckets
from overcall.proxy.writer import LogWriter


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_generate_and_hash_key():
    key, prefix = generate_key()
    assert key.startswith("oc_") and prefix == key[:9] and looks_like_key(key)
    assert hash_key(key, "p" * 32) == hash_key(key, "p" * 32)
    assert hash_key(key, "p" * 32) != hash_key(key, "q" * 32)
    assert key not in hash_key(key, "p" * 32)


@pytest.mark.parametrize(
    "value", ["", "sk-abc", "oc_", "oc_" + "x" * 200, "oc_ÃÂºÃÂ»Ã‘Å½Ã‘â€¡_key_key"]
)
def test_looks_like_key_rejects(value):
    assert not looks_like_key(value)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/v1/chat/completions", "/v1/chat/completions"),
        ("/v1/models", "/v1/models"),
        ("/v1/customers/cus_Abc123XyZ", "/v1/customers/{id}"),
        ("/v1/payment_intents/pi_3Nabc12345", "/v1/payment_intents/{id}"),
        ("/v1/charges/12345", "/v1/charges/{id}"),
        ("/v1/x/123e4567-e89b-12d3-a456-426614174000", "/v1/x/{id}"),
        ("/v1/x/0123456789abcdef0123", "/v1/x/{id}"),
        ("/v1/embeddings", "/v1/embeddings"),
    ],
)
def test_normalize_endpoint(path, expected):
    assert normalize_endpoint(path) == expected


def test_caller_label():
    assert clean_caller("billing-svc") == "billing-svc"
    assert clean_caller("bad value!") is None
    assert clean_caller("x" * 65) is None
    assert clean_caller(None) is None


def test_request_hash_is_key_order_independent_and_stable():
    a = request_hash("POST", "/v1/x", "b=2&a=1", b'{"a":1,"b":[1,2]}', "application/json")
    b = request_hash("post", "/v1/x", "a=1&b=2", b'{ "b": [1, 2], "a": 1 }', "application/json")
    assert a == b and len(a) == 16
    expected = hashlib.sha256(b'POST|/v1/x|a=1&b=2|{"a":1,"b":[1,2]}').hexdigest()[:16]
    assert a == expected
    assert a != request_hash("POST", "/v1/x", "a=1&b=2", b'{"a":2}', "application/json")


def test_request_hash_falls_back_to_raw_bytes():
    assert (
        request_hash("POST", "/v1/x", "", b"{not json", "application/json")
        == hashlib.sha256(b"POST|/v1/x||{not json").hexdigest()[:16]
    )
    assert (
        request_hash("GET", "/v1/x", "", b"", "") == hashlib.sha256(b"GET|/v1/x||").hexdigest()[:16]
    )


def test_request_hash_form_bodies_preserve_duplicates():
    one = request_hash("POST", "/v1/x", "", b"b=2&a=1&a=0", "application/x-www-form-urlencoded")
    two = request_hash("POST", "/v1/x", "", b"a=0&a=1&b=2", "application/x-www-form-urlencoded")
    assert one == two


def test_upstream_header_policy_keeps_repeats_and_strips_internal():
    out = upstream_request_headers(
        [
            ("Host", "x"),
            ("X-Overcall-Key", "oc_secret"),
            ("X-Overcall-Caller", "a"),
            ("Connection", "close, X-Custom"),
            ("X-Custom", "1"),
            ("X-Forwarded-For", "1.1.1.1"),
            ("Accept-Encoding", "gzip"),
            ("Authorization", "Bearer sk-1"),
            ("X-Multi", "a"),
            ("X-Multi", "b"),
            ("Forwarded", "for=1"),
            ("Content-Length", "5"),
        ],
        drop_authorization=False,
    )
    names = [n.lower() for n, _ in out]
    assert names.count("x-multi") == 2 and "authorization" in names
    for dropped in (
        "host",
        "x-overcall-key",
        "x-custom",
        "x-forwarded-for",
        "forwarded",
        "connection",
    ):
        assert dropped not in names
    assert ("accept-encoding", "identity") in out
    mock = upstream_request_headers([("Authorization", "Bearer z")], drop_authorization=True)
    assert "authorization" not in [n for n, _ in mock]


def test_response_header_policy():
    out = client_response_headers(
        [
            ("Content-Length", "1"),
            ("Content-Encoding", "gzip"),
            ("Retry-After", "3"),
            ("Set-Cookie", "a=1"),
            ("Set-Cookie", "b=2"),
            ("Transfer-Encoding", "chunked"),
            ("X-Overcall-Request-Id", "spoof"),
        ],
        "req_1",
    )
    names = [n.lower() for n, _ in out]
    assert names.count("set-cookie") == 2 and "retry-after" in names
    assert "content-length" not in names and "transfer-encoding" not in names
    assert [v for n, v in out if n == "x-overcall-request-id"] == ["req_1"]


def test_extract_openai():
    system = "s" * 250
    req = extract_openai_request(
        json.dumps(
            {
                "model": "gpt-4o",
                "stream": True,
                "tools": [{}],
                "messages": [{"role": "system", "content": system}],
            }
        ).encode(),
        "application/json",
    )
    assert req["model"] == "gpt-4o" and req["stream"] and req["uses_tools"]
    assert len(req["context_hash"]) == 16 and req["context_tokens"] == 63
    assert extract_openai_request(b"{bad", "application/json") == {}
    assert extract_openai_request(b'{"model":"x"}', "text/plain") == {}
    resp = extract_openai_response(
        b'{"usage":{"prompt_tokens":5,"completion_tokens":7,"prompt_tokens_details":{"cached_tokens":2}}}',
        "application/json",
    )
    assert resp == {"prompt_tokens": 5, "completion_tokens": 7, "cached_prompt_tokens": 2}
    assert (
        extract_openai_response(
            b'{"usage":{"prompt_tokens":-1,"completion_tokens":true}}', "application/json"
        )
        == {}
    )


def test_extract_stripe():
    assert extract_stripe({"limit": "100"}, b'{"data":[1,2,3]}', "application/json") == {
        "list_limit": 100,
        "items_returned": 3,
    }
    assert extract_stripe({"limit": "x"}, b"", None) == {}


@pytest.mark.asyncio
async def test_authenticator_paths_and_rotation():
    old, new = "o" * 32, "n" * 32
    key, _ = generate_key()
    record = KeyRecord(uuid4(), uuid4(), False)
    store = {hash_key(key, old): record}
    calls: list[str] = []

    class Store:
        async def find(self, h):
            calls.append(h)
            return store.get(h)

    clock = Clock()
    auth = IngestAuthenticator(Store(), new, old, clock=clock)
    assert await auth.authenticate(key) == record
    await auth.authenticate(key)
    assert len(calls) == 2  # new-pepper miss + prev hit, then cached
    for header, code in [
        (None, "ingest_key_missing"),
        ("  ", "ingest_key_missing"),
        ("junk", "ingest_key_invalid"),
        ("oc_" + "z" * 20, "ingest_key_invalid"),
    ]:
        with pytest.raises(OvercallError) as exc:
            await auth.authenticate(header)
        assert exc.value.code == code
    store[hash_key(key, old)] = KeyRecord(record.id, record.user_id, True)
    clock.t += 61
    with pytest.raises(OvercallError) as exc:
        await auth.authenticate(key)
    assert exc.value.code == "ingest_key_revoked"
    with pytest.raises(OvercallError) as exc:
        await IngestAuthenticator(Store(), None).authenticate(key)
    assert exc.value.code == "not_ready"


@pytest.mark.asyncio
async def test_previous_pepper_is_rehashed_to_current_version():
    previous, current = "o" * 32, "n" * 32
    key, _ = generate_key()
    record = KeyRecord(uuid4(), uuid4(), False, pepper_version=1)
    stored = {hash_key(key, previous): record}

    class Store:
        async def find(self, key_hash):
            return stored.get(key_hash)

        async def rehash(self, key_id, old_hash, new_hash, pepper_version):
            old = stored.pop(old_hash)
            stored[new_hash] = KeyRecord(
                old.id, old.user_id, old.revoked, pepper_version=pepper_version
            )

    auth = IngestAuthenticator(Store(), current, previous, pepper_version=2)
    assert await auth.authenticate(key) == record
    assert hash_key(key, previous) not in stored
    assert stored[hash_key(key, current)].pepper_version == 2


@pytest.mark.asyncio
async def test_negative_cache_expires():
    key, _ = generate_key()
    store: dict = {}
    seen = []

    class Store:
        async def find(self, h):
            seen.append(h)
            return store.get(h)

    clock = Clock()
    auth = IngestAuthenticator(Store(), "p" * 32, clock=clock)
    with pytest.raises(OvercallError):
        await auth.authenticate(key)
    store[hash_key(key, "p" * 32)] = KeyRecord(uuid4(), uuid4(), False)
    with pytest.raises(OvercallError):
        await auth.authenticate(key)
    clock.t += 11
    assert (await auth.authenticate(key)).revoked is False


def test_token_bucket_refills():
    clock = Clock()
    buckets = TokenBuckets(rate=1, burst=2, clock=clock)
    assert buckets.allow("k") and buckets.allow("k") and not buckets.allow("k")
    assert buckets.allow("other")
    clock.t += 1
    assert buckets.allow("k") and not buckets.allow("k")


def test_failed_auth_throttle_and_inflight():
    clock = Clock()
    throttle = FailedAuthThrottle(limit=3, window=60, clock=clock)
    for _ in range(3):
        assert not throttle.blocked("ip")
        throttle.record_failure("ip")
    assert throttle.blocked("ip") and not throttle.blocked("other")
    clock.t += 61
    assert not throttle.blocked("ip")
    cap = InflightCap(2)
    assert cap.acquire() and cap.acquire() and not cap.acquire()
    cap.release()
    assert cap.acquire()


@pytest.mark.asyncio
async def test_writer_batches_and_flushes_on_stop():
    batches: list[int] = []

    async def sink(rows):
        batches.append(len(rows))

    writer = LogWriter(sink, batch_size=3, flush_interval=0.05)
    for i in range(7):
        writer.submit({"i": i})
    writer.start()
    await writer.stop()
    assert sum(batches) == 7 and max(batches) <= 3 and writer.dropped == 0


@pytest.mark.asyncio
async def test_writer_drops_when_full():
    async def sink(rows):
        return None

    writer = LogWriter(sink, queue_max=2)
    assert writer.submit({}) and writer.submit({}) and not writer.submit({})
    assert writer.dropped == 1


@pytest.mark.asyncio
async def test_writer_retries_then_drops():
    attempts = 0

    async def sink(rows):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("db down")

    writer = LogWriter(sink, flush_interval=0.02, retry_delays=(0.01, 0.01))
    writer.submit({"a": 1})
    writer.start()
    for _ in range(100):
        if writer.dropped:
            break
        await asyncio.sleep(0.02)
    await writer.stop()
    assert attempts == 3 and writer.dropped == 1


@pytest.mark.asyncio
async def test_writer_retry_succeeds():
    attempts = 0
    seen = []

    async def sink(rows):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("blip")
        seen.extend(rows)

    writer = LogWriter(sink, flush_interval=0.02, retry_delays=(0.01,))
    writer.submit({"a": 1})
    writer.start()
    for _ in range(100):
        if seen:
            break
        await asyncio.sleep(0.02)
    await writer.stop()
    assert seen == [{"a": 1}] and writer.dropped == 0
