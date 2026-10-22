from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth.ingest_keys import generate_key, hash_key
from ...config import Settings
from ...db.models import IngestKey
from ...deps import UserContext, current_user, get_app_settings, get_session
from ...errors import OvercallError
from ..schemas import CreatedIngestKey, IngestKeyCreate, IngestKeyOut, IngestKeyPage

router = APIRouter(tags=["ingest keys"])
MAX_ACTIVE_KEYS = 5


@router.post("/ingest-keys", response_model=CreatedIngestKey, status_code=201)
async def create_ingest_key(
    body: IngestKeyCreate,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> CreatedIngestKey:
    if settings.ingest_key_pepper is None:
        raise OvercallError("not_ready", 503, "The service is not ready. Try again shortly.")

    await session.execute(
        text("select pg_advisory_xact_lock(hashtextextended(:user_id, 0))"),
        {"user_id": str(user.user_id)},
    )
    active_count = await session.scalar(
        select(func.count())
        .select_from(IngestKey)
        .where(IngestKey.user_id == user.user_id, IngestKey.revoked_at.is_(None))
    )
    if (active_count or 0) >= MAX_ACTIVE_KEYS:
        raise OvercallError("conflict", 409, "Revoke an active key before creating another.")

    key, prefix = generate_key()
    row = IngestKey(
        user_id=user.user_id,
        name=body.name,
        prefix=prefix,
        key_hash=hash_key(key, settings.ingest_key_pepper.get_secret_value()),
        pepper_version=settings.ingest_key_pepper_version,
    )
    session.add(row)
    await session.flush()
    await session.commit()
    return CreatedIngestKey(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        key=key,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


@router.get("/ingest-keys", response_model=IngestKeyPage)
async def list_ingest_keys(
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> IngestKeyPage:
    rows = await session.scalars(
        select(IngestKey)
        .where(IngestKey.user_id == user.user_id)
        .order_by(IngestKey.created_at.desc(), IngestKey.id.desc())
    )
    return IngestKeyPage(
        items=[
            IngestKeyOut(
                id=row.id,
                name=row.name,
                prefix=row.prefix,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
                revoked_at=row.revoked_at,
            )
            for row in rows
        ],
        next_cursor=None,
    )


@router.delete("/ingest-keys/{key_id}", status_code=204)
async def revoke_ingest_key(
    key_id: UUID,
    request: Request,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await session.execute(
        update(IngestKey)
        .where(
            IngestKey.id == key_id,
            IngestKey.user_id == user.user_id,
            IngestKey.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
    proxy = request.app.state.proxy
    if proxy is not None:
        proxy.authenticator.evict_key(key_id)
    return Response(status_code=204)
