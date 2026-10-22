from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import DetectionRun, RequestLog
from ...db.models import Issue as IssueModel
from ...db.repos.settings import SettingsRepository
from ...deps import UserContext, current_user, get_session
from ..common import impact_order, issue_to_schema
from ..schemas import (
    ExperimentalSavings,
    Overview,
    OverviewWindow,
    ProviderBreakdown,
    ReliabilityFindings,
    SeverityBreakdown,
    SpendSavings,
    TrendPoint,
    usd,
)

router = APIRouter(tags=["overview"])

PROVIDER_ORDER = ("openai", "stripe", "aws")


def _empty() -> Overview:
    return Overview(
        has_data=False,
        is_demo_data=False,
        generated_at=None,
        run_id=None,
        window=OverviewWindow(start=None, end=None, days=0.0, low_confidence_projection=False),
        request_count=0,
        flagged_request_count=0,
        total_spend_usd=0.0,
        spend_savings=SpendSavings(window_usd=0.0, projected_monthly_usd=0.0, percent_of_spend=0.0),
        experimental_spend_savings=ExperimentalSavings(projected_monthly_usd=0.0),
        reliability_findings=ReliabilityFindings(count=0, modelled_overhead_monthly_usd=0.0),
        severity_breakdown=SeverityBreakdown(),
        by_provider=[],
        trend=[],
        top_issues=[],
    )


@router.get("/overview", response_model=Overview)
async def get_overview(
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Overview:
    run = await session.scalar(
        select(DetectionRun)
        .where(DetectionRun.user_id == user.user_id, DetectionRun.status == "succeeded")
        .order_by(DetectionRun.started_at.desc(), DetectionRun.id)
        .limit(1)
    )
    if run is None or run.request_count == 0:
        return _empty()

    settings = await SettingsRepository(session, user.user_id).get_or_create()
    visible = IssueModel.experimental.is_(False)

    spend_by_provider: dict[str, Decimal] = defaultdict(Decimal)
    if run.window_start and run.window_end:
        spend_rows = await session.execute(
            select(RequestLog.provider, func.coalesce(func.sum(RequestLog.cost_usd), 0))
            .where(
                RequestLog.user_id == user.user_id,
                RequestLog.source == ("demo" if run.is_demo_data else "proxy"),
                RequestLog.occurred_at >= run.window_start,
                RequestLog.occurred_at <= run.window_end,
                RequestLog.cost_basis.in_(("billed", "estimated")),
            )
            .group_by(RequestLog.provider)
        )
        for provider, total in spend_rows:
            spend_by_provider[provider] = Decimal(total)
    issue_rows = await session.execute(
        select(IssueModel.provider, func.count())
        .where(IssueModel.user_id == user.user_id, visible)
        .group_by(IssueModel.provider)
    )
    issues_by_provider = dict(issue_rows.all())
    top = (
        await session.scalars(
            select(IssueModel)
            .where(IssueModel.user_id == user.user_id, visible)
            .order_by(*impact_order())
            .limit(5)
        )
    ).all()
    await session.commit()

    counts = {
        key: int((run.issue_counts or {}).get(key, 0)) for key in ("critical", "warning", "info")
    }
    spend = run.total_spend_usd or Decimal(0)
    savings = run.spend_savings_window_usd or Decimal(0)
    percent = float(round(savings / spend * 100, 1)) if spend else 0.0
    providers = [
        provider
        for provider in PROVIDER_ORDER
        if provider in spend_by_provider or provider in issues_by_provider
    ]
    return Overview(
        has_data=True,
        is_demo_data=run.is_demo_data,
        generated_at=run.finished_at or run.started_at,
        run_id=run.id,
        window=OverviewWindow(
            start=run.window_start,
            end=run.window_end,
            days=float(run.window_days or 0),
            low_confidence_projection=run.projection_low_confidence,
        ),
        request_count=run.request_count,
        flagged_request_count=run.flagged_request_count,
        total_spend_usd=usd(spend),
        spend_savings=SpendSavings(
            window_usd=usd(savings),
            projected_monthly_usd=usd(run.spend_savings_monthly_usd),
            percent_of_spend=percent,
        ),
        experimental_spend_savings=ExperimentalSavings(
            projected_monthly_usd=usd(run.experimental_monthly_usd if settings.tier3_enabled else 0)
        ),
        reliability_findings=ReliabilityFindings(
            count=run.reliability_count,
            modelled_overhead_monthly_usd=usd(run.reliability_overhead_monthly_usd),
        ),
        severity_breakdown=SeverityBreakdown(**counts),
        by_provider=[
            ProviderBreakdown(
                provider=provider,
                spend_usd=usd(spend_by_provider.get(provider)),
                issue_count=issues_by_provider.get(provider, 0),
            )
            for provider in providers
        ],
        trend=[
            TrendPoint(
                date=point["date"],
                spend_usd=float(point["spend_usd"]),
                waste_usd=float(point["waste_usd"]),
            )
            for point in (run.trend or [])
        ],
        top_issues=[issue_to_schema(item) for item in top],
    )
