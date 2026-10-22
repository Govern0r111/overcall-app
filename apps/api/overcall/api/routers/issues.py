from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Issue as IssueModel
from ...db.models import IssueRequest, RequestLog
from ...db.repos.settings import SettingsRepository
from ...deps import UserContext, current_user, get_session
from ...errors import OvercallError
from ..common import experimental_visible, impact_order, issue_to_schema
from ..pagination import DEFAULT_LIMIT, decode_cursor, encode_cursor
from ..schemas import Issue, IssueDetail, Page, SampleRequest, usd

router = APIRouter(tags=["issues"])

MAX_SAMPLES = 5


def _not_found() -> OvercallError:
    return OvercallError("not_found", 404, "The requested item was not found.")


@router.get("/issues", response_model=Page[Issue])
async def list_issues(
    provider: Literal["openai", "stripe", "aws"] | None = None,
    severity: Literal["critical", "warning", "info"] | None = None,
    tier: int | None = Query(None, ge=1, le=3),
    impact_kind: Literal["spend", "reliability"] | None = None,
    include_experimental: bool = False,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=200),
    cursor: str | None = None,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[Issue]:
    settings = await SettingsRepository(session, user.user_id).get_or_create()
    conditions = [
        IssueModel.user_id == user.user_id,
        experimental_visible(settings.tier3_enabled, include_experimental),
    ]
    if provider:
        conditions.append(IssueModel.provider == provider)
    if severity:
        conditions.append(IssueModel.severity == severity)
    if tier:
        conditions.append(IssueModel.tier == tier)
    if impact_kind:
        conditions.append(IssueModel.impact_kind == impact_kind)

    rows = (
        await session.scalars(select(IssueModel).where(*conditions).order_by(*impact_order()))
    ).all()
    await session.commit()

    start = 0
    if cursor is not None:
        _, cursor_id = decode_cursor(cursor)
        position = next((index for index, row in enumerate(rows) if row.id == cursor_id), None)
        if position is None:
            raise OvercallError("invalid_cursor", 400, "The page cursor is not valid. Start again.")
        start = position + 1
    page = rows[start : start + limit]
    more = start + limit < len(rows)
    return Page[Issue](
        items=[issue_to_schema(row) for row in page],
        next_cursor=encode_cursor(page[-1].detected_at, page[-1].id) if more and page else None,
    )


@router.get("/issues/{issue_id}", response_model=IssueDetail)
async def get_issue(
    issue_id: UUID,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> IssueDetail:
    settings = await SettingsRepository(session, user.user_id).get_or_create()
    row = await session.scalar(
        select(IssueModel).where(
            IssueModel.id == issue_id,
            IssueModel.user_id == user.user_id,
            experimental_visible(settings.tier3_enabled, True),
        )
    )
    if row is None:
        await session.rollback()
        raise _not_found()
    samples = (
        await session.execute(
            select(RequestLog)
            .join(IssueRequest, IssueRequest.request_id == RequestLog.id)
            .where(
                IssueRequest.issue_id == issue_id,
                IssueRequest.user_id == user.user_id,
                RequestLog.user_id == user.user_id,
            )
            .order_by(IssueRequest.waste_usd.desc(), RequestLog.occurred_at, RequestLog.id)
            .limit(MAX_SAMPLES)
        )
    ).scalars()
    detail = IssueDetail(
        **issue_to_schema(row).model_dump(),
        sample_requests=[
            SampleRequest(
                request_id=log.id,
                occurred_at=log.occurred_at,
                req_hash=log.req_hash,
                req_size=log.req_size,
                resp_size=log.resp_size,
                status=log.status,
                cost_usd=usd(log.cost_usd),
            )
            for log in samples
        ],
    )
    await session.commit()
    return detail
