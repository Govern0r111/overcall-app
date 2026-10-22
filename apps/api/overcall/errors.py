from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging import get_logger, get_request_id

logger = get_logger(__name__)
_CONTRACT_ERRORS = Path(__file__).resolve().parents[3] / "contract" / "errors.json"


def load_error_catalog(path: Path = _CONTRACT_ERRORS) -> dict[str, dict[str, Any]]:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load the Overcall error catalog at {path}") from exc
    if not isinstance(catalog, dict) or not catalog:
        raise RuntimeError("The Overcall error catalog must be a non-empty object")
    for code, definition in catalog.items():
        if (
            not isinstance(code, str)
            or not isinstance(definition, dict)
            or not isinstance(definition.get("status"), int)
            or not isinstance(definition.get("message"), str)
        ):
            raise RuntimeError(f"Invalid error catalog entry: {code!r}")
    return catalog


ERROR_CATALOG = load_error_catalog()


@dataclass
class OvercallError(Exception):
    code: str
    status: int
    message: str
    details: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        definition = ERROR_CATALOG.get(self.code)
        if definition is None:
            raise ValueError(f"Unknown Overcall error code: {self.code}")
        if self.status != definition["status"]:
            raise ValueError(f"Status for {self.code} must be {definition['status']}")
        if not self.message:
            raise ValueError("Overcall errors require a safe, non-empty message")
        Exception.__init__(self, self.message)


def _error_response(
    code: str,
    status: int,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": get_request_id(),
    }
    if details:
        error["details"] = details
    return JSONResponse(status_code=status, content={"error": error})


def _catalog_error(code: str) -> tuple[int, str]:
    definition = ERROR_CATALOG.get(code)
    if definition is None:
        raise RuntimeError(f"Unknown Overcall error code: {code}")
    return definition["status"], definition["message"]


async def overcall_error_handler(_request: Request, exc: OvercallError) -> JSONResponse:
    return _error_response(exc.code, exc.status, exc.message, exc.details)


async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code_by_status = {
        400: "confirmation_required",
        401: "unauthenticated",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        429: "rate_limited",
        501: "provider_not_supported",
        502: "upstream_unreachable",
        503: "not_ready",
        504: "upstream_timeout",
    }
    code = code_by_status.get(exc.status_code, "internal_error")
    status, message = _catalog_error(code)
    if status != exc.status_code:
        status, message = _catalog_error("internal_error")
        code = "internal_error"
    return _error_response(code, status, message)


async def validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    fields = []
    for issue in exc.errors():
        path = ".".join(str(part) for part in issue.get("loc", ()) if part != "body")
        fields.append({"path": path, "message": "Invalid value."})
    _, message = _catalog_error("validation_error")
    return _error_response("validation_error", 422, message, {"fields": fields})


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    route = request.scope.get("route")
    logger.error(
        "Unhandled request exception route=%s",
        getattr(route, "path", "unmatched"),
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    _, message = _catalog_error("internal_error")
    return _error_response("internal_error", 500, message)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(OvercallError, overcall_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
