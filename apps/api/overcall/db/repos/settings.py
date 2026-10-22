from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ...detection.registry import RULES
from ...detection.thresholds import Thresholds
from ..models import UserSettings


class SettingsRepository:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    async def get_or_create(self) -> UserSettings:
        await self.session.execute(
            pg_insert(UserSettings).values(user_id=self.user_id).on_conflict_do_nothing()
        )
        row = await self.session.scalar(
            select(UserSettings)
            .where(UserSettings.user_id == self.user_id)
            .execution_options(populate_existing=True)
        )
        assert row is not None
        return row

    async def get_upstream_mode(self) -> str:
        row = await self.session.scalar(
            select(UserSettings.upstream_mode).where(UserSettings.user_id == self.user_id)
        )
        return row or "mock"


def effective_rules(row: UserSettings) -> dict[str, bool]:
    return {rule.id: bool(row.rules_enabled.get(rule.id, rule.default_enabled)) for rule in RULES}


def effective_thresholds(row: UserSettings) -> dict[str, Any]:
    return Thresholds.model_validate(row.thresholds or {}).model_dump(mode="json")
