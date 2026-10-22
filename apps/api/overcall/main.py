from __future__ import annotations

import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.responses import Response

from .config import Settings, get_settings
from .db.engine import create_database_engine
from .errors import OvercallError, register_error_handlers, unhandled_error_handler
from .logging import configure_logging, get_logger, reset_request_id, set_request_id

logger = get_logger(__name__)


class VersionedCorsMiddleware:
    def __init__(self, app, settings: Settings) -> None:
        self.app = app
        self.cors_app = CORSMiddleware(
            app,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Overcall-Request-Id"],
        )

    async def __call__(self, scope, receive, send) -> None:
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/v1" or path.startswith("/v1/")):
            await self.cors_app(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(app_settings.log_level)
        app.state.engine = create_database_engine(app_settings)
        try:
            yield
        finally:
            if app.state.engine is not None:
                await app.state.engine.dispose()

    app = FastAPI(
        title="Overcall API",
        version=app_settings.release,
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.engine = None
    register_error_handlers(app)
    app.add_middleware(VersionedCorsMiddleware, settings=app_settings)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        request_id = f"req_{uuid4().hex}"
        token = set_request_id(request_id)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                response = await unhandled_error_handler(request, exc)
            response.headers["X-Overcall-Request-Id"] = request_id
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            logger.info(
                "request_complete method=%s route=%s status=%s duration_ms=%.2f",
                request.method,
                route_path,
                response.status_code,
                (time.perf_counter() - started) * 1000,
            )
            return response
        finally:
            reset_request_id(token)

    @app.get("/healthz", include_in_schema=True)
    async def health() -> dict[str, str]:
        return {"status": "ok", "release": app_settings.release}

    @app.get("/readyz", include_in_schema=True)
    async def readiness(request: Request) -> dict[str, str]:
        engine = request.app.state.engine
        if engine is None:
            raise OvercallError("not_ready", 503, "The service is not ready. Try again shortly.")
        try:
            async with engine.connect() as connection:
                await connection.execute(text("select 1"))
        except Exception as exc:
            logger.warning("Database readiness check failed: %s", type(exc).__name__)
            raise OvercallError(
                "not_ready", 503, "The service is not ready. Try again shortly."
            ) from exc
        return {"status": "ok"}

    return app


app = create_app()
