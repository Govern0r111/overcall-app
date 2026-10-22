from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from overcall.config import Settings
from overcall.deps import UserContext, current_user
from overcall.main import create_app

DEFAULT_THRESHOLDS: dict = {}


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
def users() -> Iterator[tuple[UUID, UUID]]:
    first, second = uuid4(), uuid4()

    async def create(conn):
        for user in (first, second):
            await conn.execute(text("insert into auth.users (id) values (:id)"), {"id": user})

    async def drop(conn):
        for user in (first, second):
            await conn.execute(text("delete from auth.users where id = :id"), {"id": user})

    _run(create)
    yield first, second
    _run(drop)


@pytest.fixture
def api() -> Iterator[tuple[TestClient, dict[str, UUID]]]:
    settings = Settings(
        app_env="test",
        database_url=_url().replace("postgresql://", "postgresql+asyncpg://", 1),
        release="test",
    )
    app = create_app(settings)
    state: dict[str, UUID] = {}

    async def fake_user() -> UserContext:
        return UserContext(user_id=state["uid"], email="t@example.com")

    app.dependency_overrides[current_user] = fake_user
    with TestClient(app) as client:
        yield client, state


def _insert_logs(user: UUID, count: int, *, provider: str = "openai", source: str = "proxy"):
    now = datetime.now(UTC)

    async def go(conn):
        for index in range(count):
            await conn.execute(
                text(
                    """
                    insert into public.request_logs
                    (id, user_id, source, origin, occurred_at, provider, method, endpoint, status,
                     latency_ms, req_size, resp_size, req_hash, model, cost_usd, cost_basis,
                     caller, tokens_estimated, stream, has_idempotency_key)
                    values (:id, :u, :s, 'upstream', :t, :p, 'POST', :e, :st, 10, 10, 10, :h,
                            'gpt-4o-mini', 0.001, 'estimated', :c, false, false, false)
                    """
                ),
                {
                    "id": uuid4(),
                    "u": user,
                    "s": source,
                    "t": now - timedelta(seconds=index),
                    "p": provider,
                    "e": f"/v1/chat/completions{index % 3}",
                    "st": 200 if index % 2 == 0 else 500,
                    "h": f"hash{index:04d}",
                    "c": "caller-a" if index % 2 == 0 else "caller-b",
                },
            )

    _run(go)


def _get(client, state, user, path, **kwargs):
    state["uid"] = user
    return client.get(path, **kwargs)


def test_me_and_empty_overview(api, users) -> None:
    client, state = api
    me = _get(client, state, users[0], "/v1/me")
    assert me.status_code == 200
    assert me.json()["proxy_status"] == "no_key"
    assert me.json()["has_data"] is False
    overview = _get(client, state, users[0], "/v1/overview")
    assert overview.status_code == 200


def test_logs_pagination_is_stable_and_isolated(api, users) -> None:
    client, state = api
    first, second = users
    _insert_logs(first, 7)
    _insert_logs(second, 3)

    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        body = _get(client, state, first, "/v1/logs", params=params).json()
        seen += [item["id"] for item in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert pages == 3
    assert len(seen) == 7 == len(set(seen))

    other = _get(client, state, second, "/v1/logs").json()["items"]
    assert len(other) == 3
    assert not set(seen) & {item["id"] for item in other}

    stolen = _get(client, state, second, f"/v1/logs/{seen[0]}")
    assert stolen.status_code == 404
    assert stolen.json()["error"]["code"] == "not_found"
    assert _get(client, state, first, f"/v1/logs/{seen[0]}").status_code == 200


def test_logs_filters_and_edge_cases(api, users) -> None:
    client, state = api
    user = users[0]
    _insert_logs(user, 6)

    ok = _get(client, state, user, "/v1/logs", params={"status_class": "5xx"}).json()["items"]
    assert ok and all(item["status"] >= 500 for item in ok)
    by_caller = _get(client, state, user, "/v1/logs", params={"caller": "caller-a"}).json()
    assert {item["caller"] for item in by_caller["items"]} == {"caller-a"}
    by_hash = _get(client, state, user, "/v1/logs", params={"q": "hash0002"}).json()["items"]
    assert [item["req_hash"] for item in by_hash] == ["hash0002"]

    for params in ({"limit": 0}, {"limit": 201}, {"q": "x" * 500}, {"provider": "nope"}):
        assert _get(client, state, user, "/v1/logs", params=params).status_code == 422
    reversed_range = {"from": "2026-02-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"}
    assert _get(client, state, user, "/v1/logs", params=reversed_range).status_code == 422
    bad_cursor = _get(client, state, user, "/v1/logs", params={"cursor": "garbage"})
    assert bad_cursor.status_code == 400
    assert bad_cursor.json()["error"]["code"] == "invalid_cursor"

    for payload in ("' OR 1=1 --", "%", "_", "\\"):
        response = _get(client, state, user, "/v1/logs", params={"q": payload, "endpoint": payload})
        assert response.status_code == 200
        assert response.json()["items"] == []

    facets = _get(client, state, user, "/v1/logs/facets")
    assert facets.status_code == 200
    assert facets.json()["providers"][0]["value"] == "openai"


def test_settings_validation_gating_and_isolation(api, users) -> None:
    client, state = api
    first, second = users
    current = _get(client, state, first, "/v1/settings").json()
    assert current["upstream_mode"] == "mock"

    bad = {**current, "rules_enabled": {"no_such_rule": True}, "usd_inr_rate": 80}
    response = client.put("/v1/settings", json=bad)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["fields"][0]["path"] == "rules_enabled.no_such_rule"

    unknown = client.put("/v1/settings", json={**current, "surprise": 1})
    assert unknown.status_code == 422

    real = client.put("/v1/settings", json={**current, "upstream_mode": "real"})
    assert real.status_code == 403
    assert real.json()["error"]["code"] == "real_upstream_disabled"

    updated = client.put("/v1/settings", json={**current, "currency": "USD"})
    assert updated.status_code == 200
    assert _get(client, state, first, "/v1/settings").json()["currency"] == "USD"
    assert _get(client, state, second, "/v1/settings").json()["currency"] == current["currency"]

    assert client.post("/v1/settings/reset").status_code == 400
    reset = client.post("/v1/settings/reset", json={"confirm": True})
    assert reset.status_code == 200
    assert reset.json()["currency"] == current["currency"]


def test_demo_load_is_idempotent_and_spares_proxy_rows(api, users) -> None:
    client, state = api
    user = users[0]
    _insert_logs(user, 4)
    state["uid"] = user

    first = client.post("/v1/demo/load", json={"seed": 1, "days": 3})
    assert first.status_code == 200
    inserted = first.json()["inserted"]
    assert inserted > 0
    second = client.post("/v1/demo/load", json={"seed": 1, "days": 3})
    assert second.json()["inserted"] == inserted

    async def counts(conn):
        rows = await conn.execute(
            text("select source, count(*) from request_logs where user_id=:u group by source"),
            {"u": user},
        )
        return dict(rows.all())

    assert _run(counts) == {"proxy": 4, "demo": inserted}

    assert client.request("DELETE", "/v1/demo").status_code == 204
    assert _run(counts) == {"proxy": 4}

    assert client.post("/v1/demo/load", json={"days": 99}).status_code == 422
    assert client.post("/v1/demo/load", json={"seed": 1, "bogus": 1}).status_code == 422


def test_issues_listing_detail_and_isolation(api, users) -> None:
    client, state = api
    first, second = users
    state["uid"] = first
    assert client.post("/v1/demo/load", json={"seed": 7, "days": 7}).status_code == 200

    page = _get(client, state, first, "/v1/issues", params={"limit": 2}).json()
    assert len(page["items"]) <= 2
    assert all(not item["experimental"] for item in page["items"])
    all_items = _get(client, state, first, "/v1/issues", params={"limit": 200}).json()["items"]
    assert all_items

    for tier in (1, 2, 3):
        ok = _get(client, state, first, "/v1/issues", params={"tier": tier})
        assert ok.status_code == 200
        assert all(item["tier"] == tier for item in ok.json()["items"])
    for tier in (0, 4, "x"):
        assert _get(client, state, first, "/v1/issues", params={"tier": tier}).status_code == 422
    target = all_items[0]["id"]
    detail = _get(client, state, first, f"/v1/issues/{target}")
    assert detail.status_code == 200
    assert len(detail.json()["sample_requests"]) <= 5
    assert _get(client, state, second, f"/v1/issues/{target}").status_code == 404
    assert _get(client, state, second, "/v1/issues").json()["items"] == []

    walked: list[str] = []
    cursor = None
    while True:
        params = {"limit": 1, **({"cursor": cursor} if cursor else {})}
        body = _get(client, state, first, "/v1/issues", params=params).json()
        walked += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if not cursor:
            break
    assert walked == [item["id"] for item in all_items]

    missing = _get(client, state, first, f"/v1/issues/{uuid4()}")
    assert missing.status_code == 404


def test_delete_data_requires_exact_confirmation(api, users) -> None:
    client, state = api
    user = users[0]
    _insert_logs(user, 3)
    state["uid"] = user

    for body in (None, {}, {"confirm": "yes"}, {"confirm": "DELETE MY DATA"}):
        response = client.request("DELETE", "/v1/data", json=body)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "confirmation_required"
    assert len(client.get("/v1/logs").json()["items"]) == 3

    wipe = {"confirm": "delete my data"}
    assert client.request("DELETE", "/v1/data", json=wipe).status_code == 204
    assert client.get("/v1/logs").json()["items"] == []


def test_providers_status_and_snippets(api, users) -> None:
    client, state = api
    user = users[0]
    waiting = _get(client, state, user, "/v1/providers").json()
    by_id = {p["id"]: p for p in waiting}
    assert by_id["openai"]["status"] == "waiting"
    assert by_id["aws"]["status"] == "coming_soon"
    assert by_id["aws"]["snippets"] == []
    assert by_id["openai"]["snippets"]
    assert "YOUR_OVERCALL_KEY" in by_id["openai"]["snippets"][0]["code"]

    _insert_logs(user, 2)
    receiving = {p["id"]: p for p in client.get("/v1/providers").json()}
    assert receiving["openai"]["status"] == "receiving_traffic"
    assert receiving["openai"]["traffic"]["proxy"] == 2
