import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overcall.pricing import Usage, estimate_cost  # noqa: E402
from overcall.rules import RULES as DETECTION_RULES  # noqa: E402
from overcall.rules.base import RuleContext  # noqa: E402
from overcall.synthetic import generate  # noqa: E402
from overcall.synthetic.generator import SyntheticGenerator  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "contract" / "fixtures" / "synthetic" / "small"
RULE_IDS = {
    "duplicate_calls",
    "missing_cache",
    "retry_storm",
    "oversized_payload",
    "unbatched_calls",
    "token_bloat",
    "model_overuse",
}


class BaselineWindows:
    short_window_s = 10
    long_window_s = 600
    retry_min_backoff_ms = 1_000
    retry_min_attempts = 3
    oversized_bytes = 200_000
    unbatched_min_calls = 5
    unbatched_window_s = 5
    token_bloat_min_repeats = 3
    token_bloat_min_prompt_tokens = 1_500
    model_overuse_max_prompt_tokens = 800
    model_overuse_max_completion_tokens = 300


def serialize(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def test_same_inputs_are_byte_deterministic_and_seed_changes_results():
    first = generate(seed=0, days=2, start=datetime(2026, 2, 1, tzinfo=UTC))
    second = generate(seed=0, days=2, start=datetime(2026, 2, 1, tzinfo=UTC))
    other_seed = generate(seed=1, days=2, start=datetime(2026, 2, 1, tzinfo=UTC))

    assert serialize([row.model_dump(mode="json") for row in first[0]]) == serialize(
        [row.model_dump(mode="json") for row in second[0]]
    )
    assert serialize(first[1].model_dump(mode="json")) == serialize(
        second[1].model_dump(mode="json")
    )
    assert serialize([row.model_dump(mode="json") for row in first[0]]) != serialize(
        [row.model_dump(mode="json") for row in other_seed[0]]
    )


def test_logs_are_unique_ordered_and_contain_no_labels_or_bodies():
    logs, truth = generate(seed=7, days=3)
    ids = [log.id for log in logs]
    timestamps = [log.timestamp for log in logs]
    forbidden = {
        "ground_truth",
        "label",
        "labels",
        "rule",
        "request_body",
        "response_body",
        "body",
    }

    assert len(ids) == len(set(ids))
    assert timestamps == sorted(timestamps)
    assert all(timestamp.utcoffset() == timedelta(0) for timestamp in timestamps)
    assert {label.request_id for label in truth.labels} <= set(ids)
    assert all(not (forbidden & row.model_dump().keys()) for row in logs)


def test_persistable_log_record_does_not_include_ground_truth():
    logs, _truth = generate(seed=42, days=1)
    record = logs[0].to_record()

    assert record["source"] == "demo"
    assert record["id"] == logs[0].id
    assert "_id" not in record
    assert not {
        "ground_truth",
        "label",
        "labels",
        "rule",
        "request_body",
        "response_body",
        "body",
    } & record.keys()


def test_every_rule_has_positive_and_hard_negative_scenarios():
    _logs, truth = generate(seed=42, days=7)
    positive_rules = {label.rule_id for label in truth.labels if label.role == "positive"}
    negative_rules = {
        label.rule_id for label in truth.labels if label.role == "hard_negative"
    }
    patterns = {label.pattern for label in truth.labels}

    assert positive_rules == RULE_IDS
    assert negative_rules == RULE_IDS
    assert {
        "double_submit",
        "duplicate_calls_boundary_9_9s",
        "missing_cache_boundary_600s",
        "no_backoff_retries",
        "retry_storm_minimum_attempts",
        "giant_document_prompt",
        "oversized_payload_boundary_plus_one",
        "loop_of_single_embeddings",
        "repeated_system_prompt",
        "premium_model_for_tiny_task",
        "model_overuse_boundary_800_tokens",
        "semantic_duplicate_nonsemantic_metadata",
        "duplicate_after_configured_window",
        "overlapping_poll_different_cursor",
        "retry_chain_beyond_fast_threshold",
        "premium_model_above_tiny_task_threshold",
    } <= patterns
    assert {
        "semantic_duplicate_nonsemantic_metadata",
        "duplicate_after_configured_window",
        "overlapping_poll_different_cursor",
        "retry_chain_beyond_fast_threshold",
        "premium_model_above_tiny_task_threshold",
    } <= {
        label.pattern for label in truth.labels if label.role == "positive"
    }


def test_baseline_traffic_is_clean_for_every_rule():
    generator = SyntheticGenerator(
        42,
        7,
        "standard",
        datetime(2026, 1, 16, tzinfo=UTC),
    )
    generator.baseline(6_800)
    logs, truth = generator.finish()
    context = RuleContext(w=BaselineWindows(), window_days=7)

    assert truth.labels == []
    assert all(not rule.detect(logs, context) for rule in DETECTION_RULES)


def test_costs_are_computed_by_the_versioned_cost_engine():
    logs, _truth = generate(seed=42, days=1)
    for log in logs:
        usage = (
            Usage(
                prompt_tokens=log.prompt_tokens,
                completion_tokens=log.completion_tokens,
                cached_prompt_tokens=log.cached_prompt_tokens,
                tokens_estimated=log.tokens_estimated,
            )
            if log.provider == "openai"
            else None
        )
        expected = estimate_cost(
            log.provider,
            log.model,
            usage,
            log.status,
            log.timestamp,
        )
        assert log.cost_usd == float(expected.cost_usd)
        assert log.cost_basis == expected.basis
        assert log.pricing_version == expected.pricing_version


def test_small_fixture_validates_against_contract_schemas():
    logs_schema = json.loads((ROOT / "contract" / "synthetic-log.schema.json").read_text())
    truth_schema = json.loads(
        (ROOT / "contract" / "synthetic-ground-truth.schema.json").read_text()
    )
    logs = json.loads((FIXTURE_DIR / "logs.json").read_text())
    truth = json.loads((FIXTURE_DIR / "ground_truth.json").read_text())

    checker = jsonschema.FormatChecker()
    jsonschema.validate(logs, {"type": "array", "items": logs_schema}, format_checker=checker)
    jsonschema.validate(truth, truth_schema, format_checker=checker)
    assert 250 <= len(logs) <= 400


def test_standard_generation_finishes_under_three_seconds():
    started = time.perf_counter()
    logs, truth = generate(seed=42, days=7, size="standard")
    elapsed = time.perf_counter() - started

    assert 5_000 <= len(logs) <= 10_000
    assert truth.labels
    pattern_counts = Counter(label.pattern for label in truth.labels)
    assert min(pattern_counts.values()) >= 7
    assert elapsed < 3.0


def test_generation_caps_days_and_rejects_invalid_inputs():
    logs, _truth = generate(seed=42, days=30, size="standard")
    assert len(logs) <= 10_000
    with pytest.raises(ValueError):
        generate(days=31)
    with pytest.raises(ValueError):
        generate(size="large")
    with pytest.raises(ValueError):
        generate(start=datetime(2026, 1, 1))
