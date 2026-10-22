from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from overcall.api.pagination import decode_cursor, encode_cursor
from overcall.api.schemas import SettingsIn
from overcall.api.snippets import build_snippets
from overcall.errors import OvercallError
from overcall.main import create_app

ROOT = Path(__file__).resolve().parents[4]
PUBLIC_PATHS = {"/healthz", "/readyz"}


def test_cursor_round_trip() -> None:
    when, ident = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC), uuid4()
    assert decode_cursor(encode_cursor(when, ident)) == (when, ident)


@pytest.mark.parametrize(
    "raw",
    ["", "x", "!!!!", "bm90LWpzb24", "e30", "A" * 600, "eyJ0IjoiYmFkIiwiaSI6MX0"],
)
def test_bad_cursors_are_rejected(raw: str) -> None:
    with pytest.raises(OvercallError) as exc:
        decode_cursor(raw)
    assert exc.value.code == "invalid_cursor"
    assert exc.value.status == 400


def test_every_v1_route_requires_auth_by_default() -> None:
    app = create_app()
    routes = [
        r
        for r in app.routes
        if isinstance(r, APIRoute)
        and r.path not in PUBLIC_PATHS
        and not r.path.startswith("/proxy/")
    ]
    assert routes
    with TestClient(app, raise_server_exceptions=False) as client:
        for route in routes:
            assert route.path.startswith("/v1/"), route.path
            path = route.path.replace("{id}", str(uuid4()))
            for name in ("issue_id", "log_id"):
                path = path.replace("{" + name + "}", str(uuid4()))
            for method in route.methods - {"HEAD", "OPTIONS"}:
                response = client.request(method, path)
                assert response.status_code == 401, (method, route.path)
                assert response.json()["error"]["code"] == "unauthenticated"


def test_rules_catalogue_matches_contract() -> None:
    from overcall.detection.registry import RULES

    contract = json.loads((ROOT / "contract" / "rules.json").read_text(encoding="utf-8"))
    assert {r.id for r in RULES} == {r["id"] for r in contract["rules"]}


def test_snippets_follow_route_contract_and_hold_only_placeholder_key() -> None:
    routes = json.loads(
        (ROOT / "contract" / "fixtures" / "proxy" / "routes.json").read_text(encoding="utf-8")
    )
    prefixes = {r["provider"]: r["prefix"] for r in routes["routes"]}
    for provider in ("openai", "stripe"):
        snippets = build_snippets("http://localhost:8000", provider)
        assert snippets
        for snippet in snippets:
            assert routes["key_placeholder"] in snippet.code
            root = "http://localhost:8000" + prefixes[provider].removesuffix("/v1")
            assert root in snippet.code
            assert "sk-" not in snippet.code
    assert build_snippets("http://localhost:8000", "aws") == []


def test_request_schemas_forbid_unknown_fields() -> None:
    with pytest.raises(ValueError):
        SettingsIn.model_validate({"definitely_not_a_field": 1})
