from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from .auth.jwt import InvalidSupabaseToken
from .config import Settings
from .db.repos.settings import SettingsRepository
from .detection.runner import DetectionRunner
from .errors import OvercallError


@dataclass(frozen=True)
class UserContext:
    user_id: UUID
    email: str | None = None


async def current_user(request: Request) -> UserContext:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise OvercallError("unauthenticated", 401, "Sign in or provide a valid access token.")

    verifier = request.app.state.jwt_verifier
    try:
        identity = await verifier.verify(token.strip())
    except InvalidSupabaseToken as exc:
        raise OvercallError(
            "invalid_token", 401, "Your access token is invalid or expired. Sign in again."
        ) from exc

    session_factory = request.app.state.session_factory
    if session_factory is None:
        raise OvercallError("not_ready", 503, "The service is not ready. Try again shortly.")
    async with session_factory() as session:
        await SettingsRepository(session, identity.user_id).get_or_create()
        await session.commit()
    return UserContext(user_id=identity.user_id, email=identity.email)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    if factory is None:
        raise OvercallError("not_ready", 503, "The service is not ready. Try again shortly.")
    async with factory() as session:
        yield session


def get_runner(request: Request) -> DetectionRunner:
    factory = request.app.state.session_factory
    if factory is None:
        raise OvercallError("not_ready", 503, "The service is not ready. Try again shortly.")
    return DetectionRunner(factory)
