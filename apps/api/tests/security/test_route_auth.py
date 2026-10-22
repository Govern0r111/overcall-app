from __future__ import annotations

import re
from uuid import uuid4

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient


def test_every_v1_route_requires_a_valid_bearer_token(client: TestClient) -> None:
    checked = 0
    for route in client.app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/v1/"):
            continue
        path = re.sub(r"\{[^}]+\}", str(uuid4()), route.path)
        for method in route.methods - {"HEAD", "OPTIONS"}:
            response = client.request(
                method,
                path,
                json={} if method in {"POST", "PUT", "PATCH"} else None,
            )
            assert response.status_code == 401, f"{method} {path}: {response.text}"
            assert response.json()["error"]["code"] == "unauthenticated"
            checked += 1

    assert checked > 0


def test_health_routes_remain_public(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503
