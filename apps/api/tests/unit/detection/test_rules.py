from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from overcall.detection.base import LogRow, RuleContext
from overcall.detection.registry import RULES_BY_ID
from overcall.detection.rules.retry_storm import retry_chains
from overcall.detection.thresholds import Thresholds

START = datetime(2026, 10, 1, tzinfo=UTC)


def row(
    index: int,
    second: float,
    *,
    provider: str = "openai",
    endpoint: str = "/v1/chat/completions",
    method: str = "POST",
    req_hash: str = "same-request",
    status: int = 200,
    cost: str = "0.05",
    basis: str = "billed",
    origin: str = "upstream",
    idempotency: bool = False,
) -> LogRow:
    return LogRow(
        id=UUID(int=index),
        occurred_at=START + timedelta(seconds=second),
        provider=provider,
        endpoint=endpoint,
        method=method,
        status=status,
        latency_ms=100,
        req_size=200,
        resp_size=400,
        req_hash=req_hash,
        cost_usd=Decimal(cost),
        cost_basis=basis,  # type: ignore[arg-type]
        pricing_version="2026-01-15",
        source="demo",
        origin=origin,  # type: ignore[arg-type]
        has_idempotency_key=idempotency,
    )


def context(thresholds: Thresholds | None = None) -> RuleContext:
    return RuleContext(
        thresholds=thresholds or Thresholds(),
        window_days=30,
        now=START + timedelta(days=1),
    )


def flagged_ids(rule_id: str, rows: list[LogRow]) -> set[UUID]:
    findings = RULES_BY_ID[rule_id].detect(rows, context())
    return {row_id for finding in findings for row_id in finding.waste_by_request}


def test_duplicate_window_is_inclusive_at_ten_seconds():
    rows = [
        row(1, 0),
        row(2, 9.99),
        row(3, 19.99),
        row(4, 30.0),
    ]

    assert flagged_ids("duplicate_calls", rows) == {UUID(int=2), UUID(int=3)}


def test_duplicate_requires_matching_hash_and_successful_previous_response():
    rows = [
        row(1, 0, status=500),
        row(2, 0.5),
        row(3, 2, req_hash="another-request"),
    ]

    assert flagged_ids("duplicate_calls", rows) == set()


def test_duplicate_uses_ordered_timestamp_and_uuid_for_ties():
    first = row(2, 0)
    second = row(1, 0)

    findings = RULES_BY_ID["duplicate_calls"].detect([first, second], context())

    assert len(findings) == 1
    assert findings[0].affected == [first]


def test_overcall_and_aws_rows_are_ignored():
    rows = [
        row(1, 0, origin="overcall"),
        row(2, 1, provider="aws"),
        row(3, 2),
    ]

    assert flagged_ids("duplicate_calls", rows) == set()


def test_duplicate_payment_intent_without_idempotency_is_reliability_and_critical():
    rows = [
        row(
            1,
            0,
            provider="stripe",
            endpoint="/v1/payment_intents",
            basis="modelled",
            idempotency=True,
        ),
        row(
            2,
            1,
            provider="stripe",
            endpoint="/v1/payment_intents",
            basis="modelled",
            idempotency=False,
        ),
    ]

    finding = RULES_BY_ID["duplicate_calls"].detect(rows, context())[0]

    assert finding.severity == "critical"
    assert "Idempotency-Key" in finding.summary


def test_missing_cache_short_and_long_windows_have_documented_boundaries():
    stripe_path = "/v1/customers/cus_123456"
    exact_short = [
        row(10, 0, provider="stripe", endpoint=stripe_path, method="GET"),
        row(11, 10, provider="stripe", endpoint=stripe_path, method="GET"),
    ]
    inside_after_short = [
        row(20, 0, provider="stripe", endpoint=stripe_path, method="GET"),
        row(21, 10.01, provider="stripe", endpoint=stripe_path, method="GET"),
    ]
    exact_long = [
        row(30, 0, provider="stripe", endpoint=stripe_path, method="GET"),
        row(31, 600, provider="stripe", endpoint=stripe_path, method="GET"),
    ]
    over_long = [
        row(40, 0, provider="stripe", endpoint=stripe_path, method="GET"),
        row(41, 600.01, provider="stripe", endpoint=stripe_path, method="GET"),
    ]

    assert flagged_ids("missing_cache", exact_short) == set()
    assert flagged_ids("missing_cache", inside_after_short) == {UUID(int=21)}
    assert flagged_ids("missing_cache", exact_long) == {UUID(int=31)}
    assert flagged_ids("missing_cache", over_long) == set()


def test_missing_cache_requires_cacheable_endpoint_and_successful_previous_response():
    non_cacheable = [
        row(50, 0, method="POST"),
        row(51, 30, method="POST"),
    ]
    failed_before_repeat = [
        row(
            60,
            0,
            provider="stripe",
            endpoint="/v1/customers/cus_123456",
            method="GET",
            status=500,
        ),
        row(61, 30, provider="stripe", endpoint="/v1/customers/cus_123456", method="GET"),
    ]

    assert flagged_ids("missing_cache", non_cacheable) == set()
    assert flagged_ids("missing_cache", failed_before_repeat) == set()


def test_retry_storm_requires_minimum_chain_of_fast_retries():
    fast = [row(i + 70, i * 0.2, status=429) for i in range(3)]
    two_attempts = [row(i + 80, i * 0.2, status=429) for i in range(2)]
    exponential = [
        row(90, 0, status=429),
        row(91, 1, status=429),
        row(92, 3, status=429),
    ]
    exact_backoff = [
        row(100, 0, status=429),
        row(101, 1, status=429),
        row(102, 1.5, status=429),
    ]

    assert flagged_ids("retry_storm", fast) == {UUID(int=71), UUID(int=72)}
    assert flagged_ids("retry_storm", two_attempts) == set()
    assert flagged_ids("retry_storm", exponential) == set()
    assert flagged_ids("retry_storm", exact_backoff) == set()


def test_retry_chain_stops_after_successful_response():
    rows = [
        row(110, 0, status=429),
        row(111, 0.2, status=200),
        row(112, 0.4, status=429),
    ]

    assert retry_chains(rows, 1_000, 3) == []


def test_retry_storm_is_at_least_warning_even_for_modelled_zero_cost_calls():
    rows = [
        row(i + 120, i * 0.1, provider="openai", status=500, cost="0", basis="modelled")
        for i in range(3)
    ]

    findings = RULES_BY_ID["retry_storm"].detect(rows, context())

    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_repeated_rows_order_deterministically_when_timestamps_match():
    rows = [row(200 + i, 1, req_hash="tie") for i in range(4)]

    findings = RULES_BY_ID["duplicate_calls"].detect(rows, context())

    assert [request.id for request in findings[0].affected] == [
        UUID(int=201),
        UUID(int=202),
        UUID(int=203),
    ]
