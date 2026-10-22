import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SCRIPT_PATH = ROOT / "apps" / "api" / "scripts" / "evaluate.py"
SPEC = importlib.util.spec_from_file_location("overcall_evaluate", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_small_fixture_evaluation_reports_rule_metrics_and_hard_negatives():
    fixture = ROOT / "contract" / "fixtures" / "synthetic" / "small"
    truth = MODULE.GroundTruth.model_validate_json(
        (fixture / "ground_truth.json").read_text(encoding="utf-8")
    )
    logs = MODULE.regenerate_records(truth)

    report = MODULE.evaluate_dataset(logs, truth)
    by_rule = {item["rule_id"]: item for item in report["rules"]}

    assert report["requests"] == len(logs)
    assert set(by_rule) == {
        "duplicate_calls",
        "missing_cache",
        "retry_storm",
        "oversized_payload",
        "unbatched_calls",
        "token_bloat",
        "model_overuse",
    }
    for rule_id in by_rule:
        assert by_rule[rule_id]["positives"] > 0
        assert by_rule[rule_id]["true_positives"] > 0
        assert by_rule[rule_id]["hard_negatives"] > 0
        assert "precision" in by_rule[rule_id]
        assert "recall" in by_rule[rule_id]
        assert "false_positives_on_hard_negatives" in by_rule[rule_id]


def test_evaluation_baseline_gate_only_fails_on_regression():
    report = {
        "rules": [
            {"rule_id": "duplicate_calls", "precision": 0.9, "recall": 0.8},
        ]
    }
    MODULE.assert_no_regression(
        report,
        {"rules": [{"rule_id": "duplicate_calls", "precision": 0.85, "recall": 0.75}]},
    )


def test_evaluation_rejects_a_baseline_from_another_generator_version():
    with pytest.raises(SystemExit, match="generator version mismatch"):
        MODULE.assert_no_regression(
            {"generator_version": "1.1.0", "rules": []},
            {"generator_version": "1.0.0", "rules": []},
        )
