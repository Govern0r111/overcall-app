from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import SecretStr

from overcall.auth.jwt import InvalidSupabaseToken, SupabaseJWTVerifier
from overcall.config import Settings

ISSUER_URL = "https://project.supabase.co"
ISSUER = f"{ISSUER_URL}/auth/v1"
SECRET = "legacy-supabase-test-secret-with-more-than-32-chars"


def settings(secret: str | None = SECRET) -> Settings:
    return Settings(
        app_env="test",
        supabase_url=ISSUER_URL,
        supabase_jwt_secret=SecretStr(secret) if secret else None,
    )


def claims(**overrides):
    result = {
        "sub": str(uuid4()),
        "email": "user@example.test",
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 300,
    }
    result.update(overrides)
    return result


@pytest.mark.asyncio
async def test_verifies_legacy_hs256_and_returns_only_identity_claims() -> None:
    user_id = uuid4()
    token = jwt.encode(claims(sub=str(user_id)), SECRET, algorithm="HS256")
    verifier = SupabaseJWTVerifier(settings())
    try:
        identity = await verifier.verify(token)
    finally:
        await verifier.aclose()

    assert identity.email == "user@example.test"
    assert identity.user_id == user_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, secret",
    [
        (claims(aud="other"), SECRET),
        (claims(iss="https://other.example/auth/v1"), SECRET),
        ({key: value for key, value in claims().items() if key != "sub"}, SECRET),
        (claims(sub=None), SECRET),
        (claims(exp=int(time.time()) - 120), SECRET),
        ({key: value for key, value in claims().items() if key != "exp"}, SECRET),
        (claims(), "a-different-signing-secret-with-more-than-32-chars"),
    ],
)
async def test_rejects_invalid_claims_and_signatures(payload, secret) -> None:
    token = jwt.encode(payload, secret, algorithm="HS256")
    verifier = SupabaseJWTVerifier(settings())
    try:
        with pytest.raises(InvalidSupabaseToken):
            await verifier.verify(token)
    finally:
        await verifier.aclose()


@pytest.mark.asyncio
async def test_rejects_alg_none() -> None:
    token = jwt.encode(claims(), key="", algorithm="none")
    verifier = SupabaseJWTVerifier(settings())
    try:
        with pytest.raises(InvalidSupabaseToken):
            await verifier.verify(token)
    finally:
        await verifier.aclose()


@pytest.mark.asyncio
async def test_accepts_expiry_within_configured_clock_skew() -> None:
    token = jwt.encode(claims(exp=int(time.time()) - 10), SECRET, algorithm="HS256")
    verifier = SupabaseJWTVerifier(settings())
    try:
        assert (await verifier.verify(token)).user_id
    finally:
        await verifier.aclose()


@pytest.mark.asyncio
async def test_uses_cached_supabase_jwks_and_refreshes_unknown_key_ids() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    fetches = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal fetches
        fetches += 1
        return httpx.Response(200, json={"keys": [public_jwk]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    verifier = SupabaseJWTVerifier(settings(None), client)
    token = jwt.encode(claims(), private_key, algorithm="RS256", headers={"kid": "test-key"})
    unknown_key_token = jwt.encode(
        claims(), private_key, algorithm="RS256", headers={"kid": "rotated-key"}
    )
    try:
        first = await verifier.verify(token)
        second = await verifier.verify(token)
        with pytest.raises(InvalidSupabaseToken):
            await verifier.verify(unknown_key_token)
    finally:
        await verifier.aclose()
        await client.aclose()

    assert first == second
    assert fetches == 2


@pytest.mark.asyncio
async def test_cached_jwks_remains_available_during_refresh_outage() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    current_time = [0.0]
    fetches = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal fetches
        fetches += 1
        if fetches > 1:
            raise httpx.ConnectError("JWKS endpoint unavailable", request=request)
        return httpx.Response(200, json={"keys": [public_jwk]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    verifier = SupabaseJWTVerifier(
        settings(None), client, cache_seconds=1, clock=lambda: current_time[0]
    )
    token = jwt.encode(claims(), private_key, algorithm="RS256", headers={"kid": "test-key"})
    try:
        expected = await verifier.verify(token)
        current_time[0] = 2
        assert await verifier.verify(token) == expected
    finally:
        await verifier.aclose()
        await client.aclose()

    assert fetches == 2


@pytest.mark.asyncio
async def test_jwks_failure_without_cached_keys_fails_closed() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("JWKS endpoint unavailable", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(fail))
    verifier = SupabaseJWTVerifier(settings(None), client)
    token = jwt.encode(claims(), private_key, algorithm="RS256", headers={"kid": "test-key"})
    try:
        with pytest.raises(InvalidSupabaseToken):
            await verifier.verify(token)
    finally:
        await verifier.aclose()
        await client.aclose()


@pytest.mark.asyncio
async def test_rejects_hmac_signed_with_a_public_key_as_rsa_algorithm_confusion() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps(claims()).encode()).rstrip(b"=")
    signing_input = header + b"." + payload
    signature = hmac.new(public_pem, signing_input, hashlib.sha256).digest()
    token = b".".join((signing_input, base64.urlsafe_b64encode(signature).rstrip(b"="))).decode()
    verifier = SupabaseJWTVerifier(settings(None))
    try:
        with pytest.raises(InvalidSupabaseToken):
            await verifier.verify(token)
    finally:
        await verifier.aclose()
