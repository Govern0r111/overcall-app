from fastapi.testclient import TestClient

from overcall.config import Settings
from overcall.errors import ERROR_CATALOG, OvercallError
from overcall.main import create_app


def test_catalog_contains_documented_codes() -> None:
    assert "not_ready" in ERROR_CATALOG
    assert "internal_error" in ERROR_CATALOG


def test_unknown_error_codes_are_rejected() -> None:
    try:
        OvercallError("not_a_contract_code", 500, "safe")
    except ValueError as exc:
        assert "Unknown Overcall error code" in str(exc)
    else:
        raise AssertionError("Unknown error code was accepted")


def test_404_uses_contract_error_shape() -> None:
    with TestClient(create_app(Settings(app_env="test", database_url=None))) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["message"] == ERROR_CATALOG["not_found"]["message"]
    assert "request_id" in response.json()["error"]


def test_422_does_not_return_submitted_input() -> None:
    app = create_app(Settings(app_env="test", database_url=None))

    def validate(count: int) -> dict[str, int]:
        return {"count": count}

    app.add_api_route("/v1/validate", validate, methods=["GET"])
    with TestClient(app) as client:
        response = client.get("/v1/validate", params={"count": "not-an-integer"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["fields"][0]["path"] == "query.count"
    assert "input" not in response.text
    assert "not-an-integer" not in response.text


def test_unhandled_error_is_generic_and_has_no_traceback() -> None:
    app = create_app(Settings(app_env="test", database_url=None))

    @app.get("/v1/crash")
    def crash() -> None:
        raise RuntimeError("do not return this internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/v1/crash")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "do not return this internal detail" not in response.text
    assert "Traceback" not in response.text
