from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DetectionRun


class RunsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, run: DetectionRun) -> None:
        self.session.add(run)
