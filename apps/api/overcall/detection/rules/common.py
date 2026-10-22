from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import TypeVar

from ...pricing import DEFAULT_PRICING_BOOK
from ..base import LogRow
from ..savings import monthly_projection, severity_for

T = TypeVar("T")

PROVIDER_LABELS = {"openai": "OpenAI", "stripe": "Stripe", "aws": "AWS"}


def provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, provider.title())


def group_by(items: Iterable[T], key: Callable[[T], object]) -> dict[object, list[T]]:
    groups: dict[object, list[T]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    return dict(groups)


def gap_seconds(previous: LogRow, current: LogRow) -> float:
    return (current.occurred_at - previous.occurred_at).total_seconds()


def cost_by_request(rows: list[LogRow]) -> dict:
    return {row.id: max(row.cost_usd, Decimal("0")) for row in rows}


def finding_severity(
    amount: Decimal,
    window_days: float,
    *,
    critical_at: Decimal = Decimal("20"),
    warning_at: Decimal = Decimal("2"),
):
    return severity_for(
        monthly_projection(amount, window_days),
        critical_at=critical_at,
        warning_at=warning_at,
    )


def cacheable(row: LogRow) -> bool:
    if row.method == "GET":
        return True
    if row.method != "POST":
        return False
    pricing = DEFAULT_PRICING_BOOK.for_time(row.provider, row.occurred_at)
    return row.endpoint in pricing.deterministic_post_endpoints


def money_moving_endpoint(row: LogRow) -> bool:
    if row.provider != "stripe" or row.method != "POST":
        return False
    pricing = DEFAULT_PRICING_BOOK.for_time("stripe", row.occurred_at)
    known = set(pricing.legacy.get("money_moving_endpoints", []))
    known.add("/v1/payment_intents")
    return any(row.endpoint == path or row.endpoint.startswith(f"{path}/") for path in known)


def monthly_rule_severity(amount: Decimal, window_days: float, rule_id: str):
    critical_at, warning_at = (
        (Decimal("40"), Decimal("1"))
        if rule_id == "missing_cache"
        else (Decimal("20"), Decimal("2"))
    )
    return finding_severity(
        amount,
        window_days,
        critical_at=critical_at,
        warning_at=warning_at,
    )
