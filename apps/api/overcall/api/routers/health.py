from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from ...errors import OvercallError
from ...logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/healthz")
async def health(request: Request) -> dict[str, str]:
    return {"status": "ok", "release": request.app.state.settings.release}


@router.get("/readyz")
async def readiness(request: Request) -> dict[str, str]:
    engine = request.app.state.engine
    if engine is None:
        raise OvercallError("not_ready", 503, "The service is not ready. Try again shortly.")
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception as exc:
        logger.warning("Database readiness check failed: %s", type(exc).__name__)
        message = "The service is not ready. Try again shortly."
        raise OvercallError("not_ready", 503, message) from exc
    return {"status": "ok"}
