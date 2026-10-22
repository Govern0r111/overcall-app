from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import RequestLog


class LogsRepository:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    async def load_detection_window(
        self,
        since: datetime,
        limit: int = 200_000,
    ) -> tuple[list[RequestLog], str]:
        has_live_rows = await self.session.scalar(
            select(
                exists().where(
                    RequestLog.user_id == self.user_id,
                    RequestLog.source == "proxy",
                    RequestLog.origin == "upstream",
                    RequestLog.occurred_at >= since,
                )
            )
        )
        source = "proxy" if has_live_rows else "demo"
        statement = (
            select(RequestLog)
            .where(
                RequestLog.user_id == self.user_id,
                RequestLog.source == source,
                RequestLog.origin == "upstream",
                RequestLog.occurred_at >= since,
            )
            .order_by(RequestLog.occurred_at, RequestLog.id)
            .limit(limit)
        )
        rows = list((await self.session.scalars(statement)).all())
        return rows, source
