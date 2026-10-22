from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from overcall.detection.base import LogRow, RuleContext
from overcall.detection.registry import RULES, RULES_BY_ID
from overcall.detection.savings import split_by_impact
from overcall.detection.thresholds import Thresholds
from overcall.pricing import DEFAULT_PRICING_BOOK

START = datetime(2026, 10, 1, tzinfo=UTC)


def row(index: int, second: float = 0, **overrides) -> LogRow:
    values = dict(
        id=UUID(int=index),
        occurred_at=START + timedelta(seconds=second),
        provider="openai",
        method="POST",
        endpoint="/v1/chat/completions",
        status=200,
        latency_ms=100,
        req_size=2_000,
        resp_size=2_000,
        req_hash=f"hash-{index}",
        cost_usd=Decimal("0.10"),
        cost_basis="billed",
        pricing_version="2026-01-15",
        source="demo",
        origin="upstream",
        model="gpt-4o",
        prompt_tokens=400,
        completion_tokens=50,
    )
    values.update(overrides)
    return LogRow(**values)


def context(**thresholds) -> RuleContext:
    return RuleContext(
        thresholds=Thresholds(**thresholds), window_days=30, now=START + timedelta(days=1)
    )


def flagged(rule_id: str, rows: list[LogRow], **thresholds) -> set[UUID]:
    findings = RULES_BY_ID[rule_id].detect(rows, context(**thresholds))
    return {request_id for finding in findings for request_id in finding.waste_by_request}


def embed(index: int, second: float, **overrides) -> LogRow:
    return row(
        index,
        second,
        endpoint="/v1/embeddings",
        model="text-embedding-3-small",
        prompt_tokens=100,
        completion_tokens=0,
        cost_usd=Decimal("0.01"),
        **overrides,
    )


# oversized_payload


def test_oversized_payload_boundary_is_exclusive():
    rows = [row(1, req_size=200_000), row(2, req_size=200_001), row(3, resp_size=500_000)]

    assert flagged("oversized_payload", rows) == {UUID(int=2), UUID(int=3)}


def test_oversized_payload_waste_is_the_share_above_the_limit():
    rows = [row(1, req_size=400_000, cost_usd=Decimal("1.00"))]

    finding = RULES_BY_ID["oversized_payload"].detect(rows, context())[0]

    assert finding.waste_by_request[UUID(int=1)] == Decimal("0.5")


def test_oversized_payload_respects_a_custom_threshold():
    rows = [row(1, req_size=20_000)]

    assert flagged("oversized_payload", rows) == set()
    assert flagged("oversized_payload", rows, oversized_bytes=10_000) == {UUID(int=1)}


def test_oversized_payload_ignores_overcall_rows_and_aws():
    rows = [row(1, req_size=900_000, origin="overcall"), row(2, req_size=900_000, provider="aws")]

    assert flagged("oversized_payload", rows) == set()


# unbatched_calls


def test_unbatched_calls_needs_the_minimum_burst_and_flags_every_call_after_the_first():
    burst = [embed(index, index * 0.3, caller="loop") for index in range(1, 6)]

    assert flagged("unbatched_calls", burst) == {UUID(int=index) for index in range(2, 6)}


def test_unbatched_calls_four_call_burst_is_not_flagged():
    assert flagged("unbatched_calls", [embed(i, i * 0.3) for i in range(1, 5)]) == set()


def test_unbatched_calls_gap_beyond_window_breaks_the_burst():
    rows = [embed(i, i * 6) for i in range(1, 6)]

    assert flagged("unbatched_calls", rows) == set()


def test_unbatched_calls_gap_at_window_is_inclusive():
    rows = [embed(i, i * 5) for i in range(1, 6)]

    assert len(flagged("unbatched_calls", rows)) == 4


def test_unbatched_calls_separates_callers():
    rows = [embed(i, i * 0.1, caller="a" if i % 2 else "b") for i in range(1, 9)]

    assert flagged("unbatched_calls", rows) == set()


def test_unbatched_calls_skips_endpoints_without_a_batch_equivalent():
    rows = [row(i, i * 0.1) for i in range(1, 8)]

    assert flagged("unbatched_calls", rows) == set()


def test_unbatched_stripe_saving_is_reliability_never_spend():
    rows = [
        row(
            i,
            i * 0.2,
            provider="stripe",
            method="GET",
            endpoint=f"/v1/customers/cus_{i}",
            cost_usd=Decimal("0.0004"),
            cost_basis="modelled",
            model=None,
        )
        for i in range(1, 7)
    ]
    findings = RULES_BY_ID["unbatched_calls"].detect(rows, context())

    split = [part for finding in findings for part in split_by_impact(finding, 30)]

    assert split
    assert {part.impact_kind for part in split} == {"reliability"}


def test_every_batch_equivalent_documents_a_basis_for_its_saving():
    for provider in ("openai", "stripe", "aws"):
        pricing = DEFAULT_PRICING_BOOK.for_time(provider, START)
        for key, equivalent in pricing.batch_equivalents.items():
            assert equivalent.basis.strip(), key


# token_bloat


def bloat_rows(count: int, tokens: int = 1_200, model: str = "gpt-4o-mini", **overrides):
    return [
        row(
            i,
            i * 30,
            model=model,
            context_hash="ctx-a",
            context_tokens=tokens,
            cost_usd=Decimal("0.05"),
            **overrides,
        )
        for i in range(1, count + 1)
    ]


def test_token_bloat_flags_repeats_but_not_the_first_send():
    assert flagged("token_bloat", bloat_rows(4)) == {UUID(int=i) for i in (2, 3, 4)}


def test_token_bloat_needs_the_minimum_repeats():
    assert flagged("token_bloat", bloat_rows(2)) == set()
    assert len(flagged("token_bloat", bloat_rows(3))) == 2


def test_token_bloat_needs_the_minimum_context_size():
    assert flagged("token_bloat", bloat_rows(4, tokens=1_023)) == set()
    assert len(flagged("token_bloat", bloat_rows(4, tokens=1_024))) == 3


def test_token_bloat_skips_failures_and_unknown_models():
    assert flagged("token_bloat", bloat_rows(4, status=500)) == set()
    assert flagged("token_bloat", bloat_rows(4, model="mystery-model")) == set()


def test_token_bloat_waste_uses_the_cached_price_gap_and_is_clamped():
    findings = RULES_BY_ID["token_bloat"].detect(bloat_rows(4), context())
    finding = findings[0]

    expected = Decimal(1_200) * (Decimal("0.15") - Decimal("0.075")) / Decimal(1_000_000)
    assert set(finding.waste_by_request.values()) == {expected}
    assert all(
        waste <= Decimal("0.05") for waste in finding.waste_by_request.values()
    )


def test_token_bloat_is_experimental_with_bounded_confidence():
    finding = RULES_BY_ID["token_bloat"].detect(bloat_rows(4), context())[0]

    assert finding.experimental and finding.tier == 3
    assert finding.confidence == pytest.approx(0.60)
    long_run = RULES_BY_ID["token_bloat"].detect(bloat_rows(40), context())[0]
    assert long_run.confidence == 0.85


# model_overuse


def overuse_rows(count: int = 10, **overrides):
    return [
        row(i, i * 2, prompt_tokens=800, completion_tokens=300, **overrides)
        for i in range(1, count + 1)
    ]


def test_model_overuse_limits_are_inclusive_and_need_minimum_calls():
    assert len(flagged("model_overuse", overuse_rows(10))) == 10
    assert flagged("model_overuse", overuse_rows(9)) == set()


def test_model_overuse_ignores_long_prompts_long_replies_and_tools():
    assert flagged("model_overuse", overuse_rows(10, uses_tools=True)) == set()
    long_prompt = [row(i, i, prompt_tokens=801, completion_tokens=50) for i in range(1, 11)]
    long_reply = [row(i, i, prompt_tokens=100, completion_tokens=301) for i in range(1, 11)]
    assert flagged("model_overuse", long_prompt) == set()
    assert flagged("model_overuse", long_reply) == set()


def test_model_overuse_ignores_models_without_a_cheaper_sibling():
    assert flagged("model_overuse", overuse_rows(10, model="gpt-4o-mini")) == set()
    assert flagged("model_overuse", overuse_rows(10, model="unknown-model")) == set()


def test_model_overuse_waste_is_the_price_difference_at_identical_tokens():
    gpt4o = Decimal(800) * Decimal("2.5") + Decimal(300) * Decimal("10")
    mini = Decimal(800) * Decimal("0.15") + Decimal(300) * Decimal("0.6")
    full_difference = (gpt4o - mini) / Decimal(1_000_000)

    finding = RULES_BY_ID["model_overuse"].detect(
        overuse_rows(10, cost_usd=Decimal("0.01")), context()
    )[0]
    assert set(finding.waste_by_request.values()) == {full_difference}

    clamped = RULES_BY_ID["model_overuse"].detect(
        overuse_rows(10, cost_usd=Decimal("0.001")), context()
    )[0]
    assert set(clamped.waste_by_request.values()) == {Decimal("0.001")}


def test_model_overuse_confidence_depends_on_the_average_reply_length():
    short = RULES_BY_ID["model_overuse"].detect(
        [row(i, i, prompt_tokens=100, completion_tokens=20) for i in range(1, 11)], context()
    )[0]
    longer = RULES_BY_ID["model_overuse"].detect(overuse_rows(10), context())[0]

    assert short.confidence == 0.7
    assert longer.confidence == 0.55
    assert short.experimental and longer.experimental


def test_model_overuse_threshold_overrides_apply():
    rows = [row(i, i, prompt_tokens=1_000, completion_tokens=100) for i in range(1, 11)]

    assert flagged("model_overuse", rows) == set()
    assert len(flagged("model_overuse", rows, model_overuse_max_prompt_tokens=1_000)) == 10


# registry


def test_all_seven_rules_register_with_their_tiers_and_defaults():
    assert [rule.id for rule in RULES] == [
        "duplicate_calls",
        "missing_cache",
        "retry_storm",
        "oversized_payload",
        "unbatched_calls",
        "token_bloat",
        "model_overuse",
    ]
    assert {rule.id: rule.tier for rule in RULES} == {
        "duplicate_calls": 1,
        "missing_cache": 1,
        "retry_storm": 1,
        "oversized_payload": 2,
        "unbatched_calls": 2,
        "token_bloat": 3,
        "model_overuse": 3,
    }
    assert all(rule.default_enabled == (rule.tier < 3) for rule in RULES)


def test_every_rule_threshold_key_exists_on_thresholds():
    fields = set(Thresholds.model_fields)
    for rule in RULES:
        assert set(rule.threshold_keys) <= fields
