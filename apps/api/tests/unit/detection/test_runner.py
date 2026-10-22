from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from overcall.db.models import UserSettings
from overcall.detection.base import Finding, LogRow
from overcall.detection.registry import RULES
from overcall.detection.runner import _enabled_rules, _window_days, build_summary

NOW = datetime(2026, 10, 1, tzinfo=UTC)
USER = UUID(int=1)
SNAPSHOT = {"rules_enabled": {}, "tier3_enabled": False, "thresholds": {}}


def log_row(
    row_id: int,
    seconds: int,
    *,
    basis: str = "billed",
    cost: str = "1.0",
    provider: str = "openai",
) -> LogRow:
    return LogRow(
        id=UUID(int=row_id),
        occurred_at=NOW + timedelta(seconds=seconds),
        provider=provider,
        method="POST",
        endpoint="/v1/chat/completions",
        status=200,
        latency_ms=10,
        req_size=100,
        resp_size=100,
        req_hash=f"hash-{row_id}",
        cost_usd=Decimal(cost),
        cost_basis=basis,  # type: ignore[arg-type]
        pricing_version="2026-01-15",
        source="proxy",
        origin="upstream",
    )


def finding(rule_id: str, row: LogRow, waste: str, **kwargs) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity="info",
        provider=row.provider,
        endpoint=row.endpoint,
        title=rule_id,
        summary="summary",
        explanation="explanation",
        suggested_fix="fix",
        affected=[row],
        waste_by_request={row.id: Decimal(waste)},
        **kwargs,
    )


def test_settings_can_disable_every_registered_rule():
    settings = UserSettings(
        user_id=USER,
        rules_enabled={rule.id: False for rule in RULES},
    )

    assert not any(_enabled_rules(settings).values())


def test_empty_logs_create_safe_empty_summary():
    summary = build_summary(
        [],
        [],
        0,
        [],
        SNAPSHOT,
        NOW,
        NOW,
        0,
        False,
    )

    assert summary["request_count"] == 0
    assert summary["window_start"] is None
    assert summary["window_end"] is None
    assert summary["spend_savings_monthly_usd"] == Decimal("0.000000")
    assert summary["projection_low_confidence"] is False


def test_single_log_is_low_confidence_and_does_not_project_more_than_its_cost():
    row = log_row(1, 0, cost="0.5")
    issue = finding("duplicate_calls", row, "0.5")

    summary = build_summary(
        [row],
        [issue],
        _window_days([row]),
        [],
        SNAPSHOT,
        NOW,
        NOW,
        1,
        False,
    )

    assert summary["projection_low_confidence"] is True
    assert summary["spend_savings_window_usd"] == Decimal("0.500000")
    assert summary["spend_savings_monthly_usd"] == Decimal("15.000000")


def test_headline_uses_max_per_request_and_excludes_tier3_and_reliability():
    spend = log_row(2, 0, cost="0.5")
    reliability = log_row(3, 10, basis="modelled", cost="0.25")
    first_t1 = finding("duplicate_calls", spend, "0.4", tier=1)
    second_t1 = finding("retry_storm", spend, "0.3", tier=1)
    tier3 = finding(
        "experimental",
        spend,
        "0.45",
        tier=3,
        experimental=True,
    )
    reliability_issue = finding(
        "retry_storm",
        reliability,
        "0.25",
        impact_kind="reliability",
    )

    summary = build_summary(
        [spend, reliability],
        [first_t1, second_t1, tier3, reliability_issue],
        30,
        [],
        SNAPSHOT,
        NOW,
        NOW,
        1,
        False,
    )

    assert summary["spend_savings_window_usd"] == Decimal("0.400000")
    assert summary["spend_savings_monthly_usd"] == Decimal("0.400000")
    assert summary["experimental_monthly_usd"] == Decimal("0.450000")
    assert summary["reliability_count"] == 1
    assert summary["reliability_overhead_monthly_usd"] == Decimal("0.250000")
    assert summary["total_spend_usd"] == Decimal("0.500000")
    assert summary["flagged_request_count"] == 2


def test_window_span_is_zero_for_single_or_empty_rows():
    assert _window_days([]) == 0
    assert _window_days([log_row(4, 5)]) == 0
