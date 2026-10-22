from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Issue, IssueRequest


class IssuesRepository:
    def __init__(self, session: AsyncSession, user_id: UUID) -> None:
        self.session = session
        self.user_id = user_id

    async def delete_for_user(self) -> None:
        await self.session.execute(delete(Issue).where(Issue.user_id == self.user_id))

    def add_all(self, issues: list[Issue], issue_requests: list[IssueRequest]) -> None:
        self.session.add_all([*issues, *issue_requests])
