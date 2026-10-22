import pytest
from pydantic import ValidationError

from overcall.detection.registry import validate_rule_catalogue
from overcall.detection.thresholds import Thresholds, validate_contract_defaults


def test_rule_registry_matches_shared_catalogue():
    validate_rule_catalogue()


def test_threshold_model_matches_shared_contract():
    validate_contract_defaults()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("short_window_s", 0),
        ("short_window_s", 301),
        ("long_window_s", 59),
        ("long_window_s", 3601),
        ("retry_min_attempts", 1),
        ("retry_min_attempts", 11),
        ("oversized_bytes", 9_999),
        ("oversized_bytes", 5_000_001),
    ],
)
def test_threshold_out_of_bounds_are_rejected(field: str, value: int):
    with pytest.raises(ValidationError):
        Thresholds.model_validate({field: value})


def test_long_window_must_exceed_short_window():
    with pytest.raises(ValidationError, match="long_window_s"):
        Thresholds(short_window_s=60, long_window_s=60)


def test_unknown_threshold_is_rejected():
    with pytest.raises(ValidationError):
        Thresholds.model_validate({"short_window_s": 10, "not_a_threshold": 1})
