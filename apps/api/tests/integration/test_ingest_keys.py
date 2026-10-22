from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from overcall.config import Settings
from overcall.main import create_app

JWT_SECRET = "integration-test-supabase-jwt-secret-012345"
PEPPER = "integration-test-ingest-key-pepper-012345"


def _database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return value.replace("postgresql://", "postgresql+asyncpg://", 1)


def _run(coro_factory):
    async def wrapper():
        engine = create_async_engine(_database_url(), connect_args={"statement_cache_size": 0})
        try:
            async with engine.begin() as connection:
                return await coro_factory(connection)
        finally:
            await engine.dispose()

    return asyncio.run(wrapper())


@pytest.fixture
def auth_users() -> Iterator[tuple[UUID, UUID]]:
    owner, other = uuid4(), uuid4()

    async def create(connection):
        for user_id in (owner, other):
            await connection.execute(
                text("insert into auth.users (id) values (:id)"), {"id": user_id}
            )

    async def delete(connection):
        for user_id in (owner, other):
            await connection.execute(text("delete from auth.users where id = :id"), {"id": user_id})

    _run(create)
    yield owner, other
    _run(delete)


def _access_token(user_id: UUID) -> str:
    return jwt.encode(
        {
            "sub": str(user_id),
            "email": "integration@example.test",
            "aud": "authenticated",
            "iss": "https://integration.supabase.co/auth/v1",
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def test_ingest_key_create_list_revoke_and_active_limit(auth_users) -> None:
    owner, other = auth_users
    settings = Settings(
        app_env="test",
        database_url=_database_url(),
        supabase_url="https://integration.supabase.co",
        supabase_jwt_secret=JWT_SECRET,
        ingest_key_pepper=PEPPER,
        release="test",
    )
    with TestClient(create_app(settings)) as client:
        owner_headers = {"Authorization": f"Bearer {_access_token(owner)}"}
        other_headers = {"Authorization": f"Bearer {_access_token(other)}"}

        created = client.post(
            "/v1/ingest-keys", json={"name": " checkout-service "}, headers=owner_headers
        )
        assert created.status_code == 201
        body = created.json()
        key = body["key"]
        assert body["name"] == "checkout-service"
        assert key.startswith("oc_") and body["prefix"] == key[:9]
        assert len(key.removeprefix("oc_")) == 43

        listed = client.get("/v1/ingest-keys", headers=owner_headers)
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1
        assert "key" not in listed.json()["items"][0]

        async def read_stored_hash(connection):
            result = await connection.execute(
                text("select key_hash from public.ingest_keys where id = :id"),
                {"id": body["id"]},
            )
            return result.scalar_one()

        stored_hash = _run(read_stored_hash)
        assert key not in stored_hash and stored_hash != key

        settings_count = _run(
            lambda connection: connection.scalar(
                text("select count(*) from public.user_settings where user_id = :id"),
                {"id": owner},
            )
        )
        assert settings_count == 1

        # A different tenant cannot revoke this key; the response stays idempotent.
        assert (
            client.delete(f"/v1/ingest-keys/{body['id']}", headers=other_headers).status_code == 204
        )
        assert (
            client.post(
                "/proxy/openai/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "test"}]},
                headers={"X-Overcall-Key": key},
            ).status_code
            == 200
        )

        assert (
            client.delete(f"/v1/ingest-keys/{body['id']}", headers=owner_headers).status_code == 204
        )
        assert (
            client.delete(f"/v1/ingest-keys/{body['id']}", headers=owner_headers).status_code == 204
        )
        revoked = client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "test"}]},
            headers={"X-Overcall-Key": key},
        )
        assert revoked.status_code == 401
        assert revoked.json()["error"]["code"] == "ingest_key_revoked"

        assert len(client.get("/v1/ingest-keys", headers=other_headers).json()["items"]) == 0
        assert (
            client.get("/v1/ingest-keys", headers=owner_headers).json()["items"][0]["revoked_at"]
            is not None
        )
        for index in range(5):
            response = client.post(
                "/v1/ingest-keys",
                json={"name": f"service-{index}"},
                headers=owner_headers,
            )
            assert response.status_code == 201
        sixth = client.post("/v1/ingest-keys", json={"name": "service-6"}, headers=owner_headers)
        assert sixth.status_code == 409
        assert sixth.json()["error"]["code"] == "conflict"
