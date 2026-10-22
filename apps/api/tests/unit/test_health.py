from fastapi.testclient import TestClient

from overcall.config import Settings
from overcall.main import create_app


def test_health_does_not_require_database() -> None:
    with TestClient(
        create_app(Settings(app_env="test", database_url=None, release="test"))
    ) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "release": "test"}
    assert response.headers["x-overcall-request-id"].startswith("req_")


def test_readiness_returns_safe_error_when_database_is_not_configured(client: TestClient) -> None:
    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_ready"
    assert "request_id" in response.json()["error"]


def test_cors_headers_are_only_added_to_versioned_api(client: TestClient) -> None:
    origin = "http://localhost:5173"

    api_response = client.get("/v1/missing", headers={"Origin": origin})
    health_response = client.get("/healthz", headers={"Origin": origin})

    assert api_response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-origin" not in health_response.headers
