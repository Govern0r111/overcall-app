from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from overcall.auth.ingest_keys import generate_key, hash_key
from overcall.config import Settings
from overcall.main import create_app

PEPPER = "proxy-integration-pepper-0123456789abcdef"


def _url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    return value


def _run(coro_factory):
    async def wrapper():
        engine = create_async_engine(
            _url().replace("postgresql://", "postgresql+asyncpg://", 1),
            connect_args={"statement_cache_size": 0},
        )
        try:
            async with engine.begin() as connection:
                return await coro_factory(connection)
        finally:
            await engine.dispose()

    return asyncio.run(wrapper())


@pytest.fixture
def seeded() -> Iterator[tuple[UUID, UUID, str]]:
    user, key_id = uuid4(), uuid4()
    key, prefix = generate_key()

    async def create(conn):
        await conn.execute(text("insert into auth.users (id) values (:id)"), {"id": user})
        await conn.execute(
            text(
                "insert into public.ingest_keys (id, user_id, name, prefix, key_hash, "
                "pepper_version) values (:i, :u, 'test', :p, :h, 1)"
            ),
            {"i": key_id, "u": user, "p": prefix, "h": hash_key(key, PEPPER)},
        )

    async def drop(conn):
        await conn.execute(text("delete from auth.users where id = :id"), {"id": user})

    _run(create)
    yield user, key_id, key
    _run(drop)


def _rows(user: UUID) -> list[dict]:
    async def go(conn):
        result = await conn.execute(
            text("select * from public.request_logs where user_id = :u order by occurred_at"),
            {"u": user},
        )
        return [dict(r._mapping) for r in result]

    return _run(go)


def _wait_rows(user: UUID, count: int, timeout: float = 5.0) -> list[dict]:
    deadline = time.monotonic() + timeout
    rows: list[dict] = []
    while time.monotonic() < deadline:
        rows = _rows(user)
        if len(rows) >= count:
            return rows
        time.sleep(0.1)
    return rows


def _app(**overrides) -> TestClient:
    settings = Settings(
        app_env="test",
        database_url=_url().replace("postgresql://", "postgresql+asyncpg://", 1),
        release="test",
        ingest_key_pepper=PEPPER,
        **{"log_flush_interval_ms": 100, **overrides},
    )
    return TestClient(create_app(settings))


def test_proxy_request_is_stored_within_seconds(seeded) -> None:
    user, key_id, key = seeded
    sentinel = "SENTINEL-" + uuid4().hex
    with _app() as client:
        response = client.post(
            "/proxy/openai/v1/chat/completions",
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": sentinel}]},
            headers={"X-Overcall-Key": key, "Authorization": "Bearer sk-secret-value"},
        )
        assert response.status_code == 200
        rows = _wait_rows(user, 1)
    assert len(rows) == 1
    row = rows[0]
    assert row["origin"] == "upstream" and row["source"] == "proxy"
    assert row["ingest_key_id"] == key_id and row["model"] == "gpt-4o-mini"
    assert row["status"] == 200 and row["prompt_tokens"] > 0
    assert row["cost_basis"] in {"billed", "estimated"} and float(row["cost_usd"]) > 0
    assert sentinel not in str(row) and "sk-secret-value" not in str(row)

    async def key_state(conn):
        result = await conn.execute(
            text("select last_used_at from public.ingest_keys where id = :i"), {"i": key_id}
        )
        return result.scalar()

    assert _run(key_state) is not None


def test_overcall_rows_are_stored_and_ignored_by_detection(seeded) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.ext.asyncio import AsyncSession

    from overcall.db.repos.logs import LogsRepository

    user, _key_id, key = seeded
    with _app() as client:
        assert client.get("/proxy/aws/v1/x", headers={"X-Overcall-Key": key}).status_code == 501
        assert client.get("/proxy/openai/v1/x").status_code == 401
        rows = _wait_rows(user, 1)
    assert len(rows) == 1 and rows[0]["origin"] == "overcall" and rows[0]["error_code"]

    async def window():
        engine = create_async_engine(
            _url().replace("postgresql://", "postgresql+asyncpg://", 1),
            connect_args={"statement_cache_size": 0},
        )
        try:
            async with AsyncSession(engine) as session:
                return await LogsRepository(session, user).load_detection_window(
                    datetime.now(UTC) - timedelta(days=1)
                )
        finally:
            await engine.dispose()

    loaded, source = asyncio.run(window())
    assert loaded == [] and source == "demo"


def test_shutdown_flushes_pending_rows(seeded) -> None:
    user, _key_id, key = seeded
    with _app(log_flush_interval_ms=60_000) as client:
        for _ in range(5):
            client.get("/proxy/openai/v1/models", headers={"X-Overcall-Key": key})
    assert len(_rows(user)) == 5


def test_revoked_key_rejected_after_cache_expiry(seeded) -> None:
    user, key_id, key = seeded

    async def revoke(conn):
        await conn.execute(
            text("update public.ingest_keys set revoked_at = now() where id = :i"), {"i": key_id}
        )

    _run(revoke)
    with _app() as client:
        response = client.get("/proxy/openai/v1/models", headers={"X-Overcall-Key": key})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ingest_key_revoked"
    assert _rows(user) == []
