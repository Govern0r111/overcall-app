from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert, update

from ..config import Settings
from ..db.models import IngestKey, RequestLog
from ..db.repos.settings import SettingsRepository
from .ingest_auth import DbKeyStore, IngestAuthenticator
from .ratelimit import FailedAuthThrottle, InflightCap, TokenBuckets
from .router import ProxyState, build_clients
from .writer import LogWriter


def build_proxy_state(settings: Settings, session_factory) -> ProxyState:
    async def sink(rows: list[dict[str, Any]]) -> None:
        key_ids = {r["ingest_key_id"] for r in rows if r.get("ingest_key_id")}
        async with session_factory() as session:
            await session.execute(insert(RequestLog), rows)
            if key_ids:
                await session.execute(
                    update(IngestKey)
                    .where(IngestKey.id.in_(key_ids))
                    .values(last_used_at=datetime.now(UTC))
                )
            await session.commit()

    async def mode_lookup(user_id: UUID) -> str:
        async with session_factory() as session:
            return await SettingsRepository(session, user_id).get_upstream_mode()

    pepper = settings.ingest_key_pepper.get_secret_value() if settings.ingest_key_pepper else None
    prev = (
        settings.ingest_key_pepper_prev.get_secret_value()
        if settings.ingest_key_pepper_prev
        else None
    )
    return ProxyState(
        settings=settings,
        authenticator=IngestAuthenticator(
            DbKeyStore(session_factory),
            pepper,
            prev,
            pepper_version=settings.ingest_key_pepper_version,
        ),
        writer=LogWriter(
            sink,
            queue_max=settings.log_queue_max,
            batch_size=settings.log_batch_size,
            flush_interval=settings.log_flush_interval_ms / 1000,
        ),
        mode_lookup=mode_lookup,
        clients=build_clients(settings),
        buckets=TokenBuckets(settings.rate_limit_proxy_rps, settings.rate_limit_proxy_rps * 2),
        throttle=FailedAuthThrottle(),
        inflight=InflightCap(settings.max_inflight),
    )
