from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import DetectionRun, RequestLog
from ..detection.runner import LOOKBACK, DetectionRunner

logger = logging.getLogger(__name__)

INLINE_ROW_LIMIT = 20_000


async def _run_quietly(runner: DetectionRunner, user_id: UUID, run_id: UUID) -> None:
    try:
        await runner.run(user_id, run_id)
    except Exception as exc:
        logger.error("Background detection run failed error_type=%s", type(exc).__name__)


async def rerun_detection(
    session: AsyncSession,
    runner: DetectionRunner,
    background: BackgroundTasks,
    user_id: UUID,
) -> tuple[UUID, DetectionRun | None]:
    """Rerun inline for small datasets, otherwise in the background.

    Callers must commit their own changes first: the runner uses its own transaction.
    """
    since = datetime.now(UTC) - LOOKBACK - timedelta(minutes=1)
    count = await session.scalar(
        select(func.count())
        .select_from(RequestLog)
        .where(RequestLog.user_id == user_id, RequestLog.occurred_at >= since)
    )
    run_id = uuid4()
    if (count or 0) <= INLINE_ROW_LIMIT:
        return run_id, await runner.run(user_id, run_id)
    background.add_task(_run_quietly, runner, user_id, run_id)
    return run_id, None
