from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import Issue as IssueModel
from ...db.models import IssueRequest, RequestLog
from ...db.repos.settings import SettingsRepository
from ...deps import UserContext, current_user, get_session
from ...errors import OvercallError
from ..pagination import DEFAULT_LIMIT, decode_cursor, encode_cursor
from ..schemas import FacetValue, FlaggedBy, LogEntry, LogFacets, Page, usd

router = APIRouter(tags=["logs"])

MIN_HASH_PREFIX = 4
FACET_LIMIT = 100
STATUS_RANGES = {"2xx": (200, 299), "3xx": (300, 399), "4xx": (400, 499), "5xx": (500, 599)}


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _to_entry(row: RequestLog, flagged: list[FlaggedBy]) -> LogEntry:
    return LogEntry(
        id=row.id,
        occurred_at=row.occurred_at,
        provider=row.provider,
        method=row.method,
        endpoint=row.endpoint,
        status=row.status,
        latency_ms=round(float(row.latency_ms), 1),
        ttfb_ms=round(float(row.ttfb_ms), 1) if row.ttfb_ms is not None else None,
        req_size=row.req_size,
        resp_size=row.resp_size,
        req_hash=row.req_hash,
        model=row.model,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        tokens_estimated=row.tokens_estimated,
        stream=row.stream,
        cost_usd=usd(row.cost_usd),
        cost_basis=row.cost_basis,
        pricing_version=row.pricing_version,
        caller=row.caller,
        has_idempotency_key=row.has_idempotency_key,
        error_code=row.error_code,
        origin=row.origin,
        is_demo=row.source == "demo",
        flagged_by=flagged,
    )


async def _flagged_by(
    session: AsyncSession, user_id: UUID, request_ids: list[UUID], tier3_enabled: bool
) -> dict[UUID, list[FlaggedBy]]:
    if not request_ids:
        return {}
    statement = (
        select(IssueRequest.request_id, IssueModel)
        .join(IssueModel, IssueModel.id == IssueRequest.issue_id)
        .where(
            IssueRequest.user_id == user_id,
            IssueModel.user_id == user_id,
            IssueRequest.request_id.in_(request_ids),
        )
        .order_by(IssueModel.severity, IssueModel.rule_id)
    )
    if not tier3_enabled:
        statement = statement.where(IssueModel.experimental.is_(False))
    result: dict[UUID, list[FlaggedBy]] = {}
    for request_id, issue in (await session.execute(statement)).all():
        result.setdefault(request_id, []).append(
            FlaggedBy(
                issue_id=issue.id,
                rule_id=issue.rule_id,
                title=issue.title,
                severity=issue.severity,
            )
        )
    return result


async def _tier3_enabled(session: AsyncSession, user_id: UUID) -> bool:
    return (await SettingsRepository(session, user_id).get_or_create()).tier3_enabled


@router.get("/logs", response_model=Page[LogEntry])
async def list_logs(
    q: str | None = Query(None, max_length=200),
    provider: Literal["openai", "stripe", "aws"] | None = None,
    status_class: Literal["2xx", "3xx", "4xx", "5xx"] | None = None,
    endpoint: str | None = Query(None, max_length=300),
    caller: str | None = Query(None, max_length=64),
    model: str | None = Query(None, max_length=100),
    issue_id: UUID | None = None,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=200),
    cursor: str | None = None,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Page[LogEntry]:
    from_, to = _aware(from_), _aware(to)
    if from_ and to and from_ > to:
        raise OvercallError(
            "validation_error",
            422,
            "Some fields are invalid.",
            {"fields": [{"path": "from", "message": "Must not be after 'to'."}]},
        )

    conditions = [RequestLog.user_id == user.user_id]
    if q:
        text_match = [
            RequestLog.endpoint.icontains(q, autoescape=True),
            RequestLog.model.icontains(q, autoescape=True),
            RequestLog.caller.icontains(q, autoescape=True),
        ]
        if len(q) >= MIN_HASH_PREFIX:
            text_match.append(RequestLog.req_hash.istartswith(q, autoescape=True))
        conditions.append(or_(*text_match))
    if provider:
        conditions.append(RequestLog.provider == provider)
    if status_class:
        low, high = STATUS_RANGES[status_class]
        conditions.append(RequestLog.status.between(low, high))
    if endpoint:
        conditions.append(RequestLog.endpoint == endpoint)
    if caller:
        conditions.append(RequestLog.caller == caller)
    if model:
        conditions.append(RequestLog.model == model)
    if issue_id:
        conditions.append(
            exists().where(
                IssueRequest.request_id == RequestLog.id,
                IssueRequest.issue_id == issue_id,
                IssueRequest.user_id == user.user_id,
            )
        )
    if from_:
        conditions.append(RequestLog.occurred_at >= from_)
    if to:
        conditions.append(RequestLog.occurred_at <= to)
    if cursor is not None:
        cursor_time, cursor_id = decode_cursor(cursor)
        conditions.append(
            tuple_(RequestLog.occurred_at, RequestLog.id) < tuple_(cursor_time, cursor_id)
        )

    rows = (
        await session.scalars(
            select(RequestLog)
            .where(*conditions)
            .order_by(RequestLog.occurred_at.desc(), RequestLog.id.desc())
            .limit(limit + 1)
        )
    ).all()
    page = rows[:limit]
    tier3 = await _tier3_enabled(session, user.user_id)
    flagged = await _flagged_by(session, user.user_id, [row.id for row in page], tier3)
    entries = [_to_entry(row, flagged.get(row.id, [])) for row in page]
    await session.commit()
    return Page[LogEntry](
        items=entries,
        next_cursor=(
            encode_cursor(page[-1].occurred_at, page[-1].id) if len(rows) > limit else None
        ),
    )


async def _facet(session: AsyncSession, user_id: UUID, column) -> list[FacetValue]:
    rows = await session.execute(
        select(column, func.count().label("n"))
        .where(RequestLog.user_id == user_id, column.is_not(None))
        .group_by(column)
        .order_by(func.count().desc(), column)
        .limit(FACET_LIMIT)
    )
    return [FacetValue(value=value, count=count) for value, count in rows.all()]


@router.get("/logs/facets", response_model=LogFacets)
async def log_facets(
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> LogFacets:
    result = LogFacets(
        providers=await _facet(session, user.user_id, RequestLog.provider),
        endpoints=await _facet(session, user.user_id, RequestLog.endpoint),
        callers=await _facet(session, user.user_id, RequestLog.caller),
        models=await _facet(session, user.user_id, RequestLog.model),
    )
    await session.commit()
    return result


@router.get("/logs/{log_id}", response_model=LogEntry)
async def get_log(
    log_id: UUID,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> LogEntry:
    row = await session.scalar(
        select(RequestLog).where(RequestLog.id == log_id, RequestLog.user_id == user.user_id)
    )
    if row is None:
        await session.rollback()
        raise OvercallError("not_found", 404, "The requested item was not found.")
    tier3 = await _tier3_enabled(session, user.user_id)
    flagged = await _flagged_by(session, user.user_id, [row.id], tier3)
    entry = _to_entry(row, flagged.get(row.id, []))
    await session.commit()
    return entry
