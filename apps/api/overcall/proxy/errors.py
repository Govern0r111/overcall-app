from __future__ import annotations

from starlette.responses import JSONResponse

from ..errors import ERROR_CATALOG, OvercallError, _error_response


def err(code: str) -> OvercallError:
    definition = ERROR_CATALOG[code]
    return OvercallError(code, definition["status"], definition["message"])


def error_response(exc: OvercallError, retry_after: int | None = None) -> JSONResponse:
    response = _error_response(exc.code, exc.status, exc.message, exc.details)
    response.headers["x-overcall-error"] = exc.code
    if retry_after is not None:
        response.headers["retry-after"] = str(retry_after)
    return response
