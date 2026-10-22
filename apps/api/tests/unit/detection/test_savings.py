from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from overcall.detection.base import Finding, LogRow
from overcall.detection.savings import monthly_projection, split_by_impact


def test_monthly_projection_uses_minimum_one_day_window():
    assert monthly_projection(Decimal("10"), 0.25) == Decimal("300")
    assert monthly_projection(Decimal("10"), 5) == Decimal("60")


def test_mixed_cost_basis_finding_splits_spend_from_reliability():
    now = datetime(2026, 10, 1, tzinfo=UTC)
    spend_row = LogRow(
        id=UUID(int=1),
        occurred_at=now,
        provider="openai",
        method="POST",
        endpoint="/v1/chat/completions",
        status=200,
        latency_ms=1,
        req_size=1,
        resp_size=1,
        req_hash="one",
        cost_usd=Decimal("0.10"),
        cost_basis="billed",
        pricing_version="2026-01-15",
        source="proxy",
        origin="upstream",
    )
    modelled_row = LogRow(
        id=UUID(int=2),
        occurred_at=now,
        provider="openai",
        method="POST",
        endpoint="/v1/chat/completions",
        status=500,
        latency_ms=1,
        req_size=1,
        resp_size=1,
        req_hash="two",
        cost_usd=Decimal("0.04"),
        cost_basis="modelled",
        pricing_version="2026-01-15",
        source="proxy",
        origin="upstream",
    )
    finding = Finding(
        rule_id="duplicate_calls",
        severity="warning",
        provider="openai",
        endpoint="/v1/chat/completions",
        title="Repeated calls",
        summary="Summary",
        explanation="Explanation",
        suggested_fix="Fix",
        affected=[spend_row, modelled_row],
        waste_by_request={
            spend_row.id: Decimal("0.10"),
            modelled_row.id: Decimal("0.04"),
        },
    )

    spend, reliability = split_by_impact(finding, 30)

    assert spend.impact_kind == "spend"
    assert spend.affected == [spend_row]
    assert spend.window_savings_usd == Decimal("0.10")
    assert reliability.impact_kind == "reliability"
    assert reliability.affected == [modelled_row]
    assert reliability.window_savings_usd == Decimal("0.04")


def test_waste_is_capped_at_request_cost():
    row = LogRow(
        id=UUID(int=3),
        occurred_at=datetime(2026, 10, 1, tzinfo=UTC),
        provider="openai",
        method="POST",
        endpoint="/v1/chat/completions",
        status=200,
        latency_ms=1,
        req_size=1,
        resp_size=1,
        req_hash="cap",
        cost_usd=Decimal("0.02"),
        cost_basis="billed",
        pricing_version="2026-01-15",
        source="proxy",
        origin="upstream",
    )
    finding = Finding(
        rule_id="duplicate_calls",
        severity="info",
        provider="openai",
        endpoint=row.endpoint,
        title="Repeated calls",
        summary="Summary",
        explanation="Explanation",
        suggested_fix="Fix",
        affected=[row],
        waste_by_request={row.id: Decimal("1.00")},
    )

    (issue,) = split_by_impact(finding, 30)

    assert issue.waste_by_request[row.id] == Decimal("0.02")
