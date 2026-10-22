from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import RequestLog
from ...db.repos.settings import SettingsRepository
from ...deps import UserContext, current_user, get_app_settings, get_session
from ...pricing import DEFAULT_PRICING_BOOK
from ..schemas import PricingRow, Provider, ProviderPricing, ProviderTraffic
from ..snippets import build_snippets, proxy_base_url

router = APIRouter(tags=["providers"])

NAMES = {"openai": "OpenAI", "stripe": "Stripe", "aws": "AWS"}
NOTES = {
    "stripe": "Stripe does not bill per call. Savings are a modelled overhead.",
    "aws": "Coming soon.",
}


def _pricing(provider: str) -> ProviderPricing | None:
    if provider == "aws":
        return None
    book = DEFAULT_PRICING_BOOK.for_time(provider, datetime.now(UTC))
    rows: list[PricingRow] = []
    for model, price in book.models.items():
        rows.append(PricingRow(label=f"{model} input", usd_per_1m=float(price.input_per_1m)))
        rows.append(PricingRow(label=f"{model} output", usd_per_1m=float(price.output_per_1m)))
    if book.per_request_overhead_usd > 0:
        rows.append(
            PricingRow(
                label="Modelled overhead per request",
                usd_per_request=float(book.per_request_overhead_usd),
            )
        )
    return ProviderPricing(
        version=book.version,
        effective_from=book.effective_from,
        source_url=book.source_url,
        rows=rows,
    )


@router.get("/providers", response_model=list[Provider])
async def list_providers(
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    env: Settings = Depends(get_app_settings),
) -> list[Provider]:
    settings = await SettingsRepository(session, user.user_id).get_or_create()
    rows = (
        await session.execute(
            select(
                RequestLog.provider,
                RequestLog.source,
                func.count(),
                func.max(RequestLog.occurred_at),
            )
            .where(RequestLog.user_id == user.user_id)
            .group_by(RequestLog.provider, RequestLog.source)
        )
    ).all()
    await session.commit()

    traffic: dict[str, dict[str, int]] = {}
    last_seen: dict[str, datetime] = {}
    for provider, source, count, last in rows:
        traffic.setdefault(provider, {})[source] = count
        if source == "proxy" and (provider not in last_seen or last > last_seen[provider]):
            last_seen[provider] = last

    result = []
    for provider in ("openai", "stripe", "aws"):
        counts = traffic.get(provider, {})
        if provider == "aws":
            status = "coming_soon"
        elif counts.get("proxy"):
            status = "receiving_traffic"
        elif counts.get("demo"):
            status = "demo_only"
        else:
            status = "waiting"
        upstream = {"openai": settings.upstream_mode, "stripe": "test"}.get(provider)
        result.append(
            Provider(
                id=provider,
                name=NAMES[provider],
                status=status,
                proxy_base_url=None
                if provider == "aws"
                else proxy_base_url(env.public_proxy_base_url, provider),
                snippets=build_snippets(env.public_proxy_base_url, provider),
                traffic=ProviderTraffic(
                    proxy=counts.get("proxy", 0),
                    demo=counts.get("demo", 0),
                    last_request_at=last_seen.get(provider),
                ),
                upstream_mode=upstream,
                pricing=_pricing(provider),
                notes=NOTES.get(provider),
            )
        )
    return result
