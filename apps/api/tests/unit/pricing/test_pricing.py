from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from overcall.pricing import DEFAULT_PRICING_BOOK, Usage, estimate_cost, model_price
from overcall.pricing.loader import CONTRACT_SCHEMA, PRICING_FILES, PricingBook
from overcall.pricing.models import PricingFile

NOW = datetime(2026, 10, 22, tzinfo=UTC)


@pytest.mark.parametrize("provider", ("openai", "stripe", "aws"))
def test_every_pricing_file_validates_against_shared_json_schema(provider: str) -> None:
    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    entries = list((PRICING_FILES / provider).glob("*.json"))

    assert entries
    for path in entries:
        raw = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(raw)
        PricingFile.model_validate(raw)


def test_default_book_contains_all_providers_and_has_versioned_files() -> None:
    assert set(DEFAULT_PRICING_BOOK.versions) == {"openai", "stripe", "aws"}
    for provider, versions in DEFAULT_PRICING_BOOK.versions.items():
        assert versions
        assert all(entry.provider == provider for entry in versions)


def test_pricing_lookup_uses_latest_effective_version_and_preserves_history(
    tmp_path: Path,
) -> None:
    source = json.loads((PRICING_FILES / "openai" / "2026-01-15.json").read_text(encoding="utf-8"))
    earlier = dict(source, version="2026-01-15", effective_from="2026-01-15T00:00:00Z")
    later = dict(source, version="2026-06-01", effective_from="2026-06-01T00:00:00Z")
    provider_dir = tmp_path / "openai"
    provider_dir.mkdir()
    (provider_dir / "2026-01-15.json").write_text(json.dumps(earlier), encoding="utf-8")
    (provider_dir / "2026-06-01.json").write_text(json.dumps(later), encoding="utf-8")
    book = PricingBook.from_directory(tmp_path, providers=("openai",))

    before = datetime(2026, 3, 1, tzinfo=UTC)
    after = datetime(2026, 9, 1, tzinfo=UTC)
    assert book.for_time("openai", before).version == "2026-01-15"
    assert book.for_time("openai", after).version == "2026-06-01"
    with pytest.raises(ValueError, match="No openai pricing version"):
        book.for_time("openai", datetime(2025, 12, 31, tzinfo=UTC))


def test_lookup_rejects_unknown_provider_and_naive_datetime() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        DEFAULT_PRICING_BOOK.for_time("other", NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        DEFAULT_PRICING_BOOK.for_time("openai", datetime(2026, 10, 22))


def test_known_openai_model_uses_provider_usage_as_billed() -> None:
    pricing = DEFAULT_PRICING_BOOK.for_time("openai", NOW)
    model = pricing.models["gpt-4o-mini"]
    usage = Usage(prompt_tokens=1200, completion_tokens=300, cached_prompt_tokens=400)
    expected = (
        Decimal(800) * model.input_per_1m
        + Decimal(400) * model.cached_input_per_1m
        + Decimal(300) * model.output_per_1m
    ) / Decimal(1_000_000)

    result = estimate_cost("openai", "gpt-4o-mini", usage, 200, NOW)

    assert result.cost_usd == expected.quantize(Decimal("0.00000001"))
    assert result.basis == "billed"
    assert result.pricing_version == pricing.version
    assert result.fallback_used is False
    assert result.supported is True


def test_model_resolution_uses_longest_prefix() -> None:
    resolved, price = model_price("gpt-4o-mini-2024-07-18", NOW)

    assert resolved == "gpt-4o-mini"
    assert Decimal(str(price.input_per_1m)) == Decimal("0.15")


def test_unknown_model_falls_back_to_default_and_is_estimated() -> None:
    result = estimate_cost(
        "openai",
        "unknown-model-version",
        {"prompt_tokens": 100, "completion_tokens": 20},
        200,
        NOW,
    )

    assert result.fallback_used is True
    assert result.basis == "estimated"
    assert result.cost_usd > 0


def test_missing_model_uses_default_price_but_is_not_reported_as_billed() -> None:
    result = estimate_cost(
        "openai",
        None,
        {"prompt_tokens": 100, "completion_tokens": 20},
        200,
        NOW,
    )

    assert result.fallback_used is True
    assert result.basis == "estimated"


def test_tiktoken_usage_is_estimated() -> None:
    result = estimate_cost(
        "openai",
        "gpt-4o-mini",
        Usage(prompt_tokens=10, completion_tokens=5, tokens_estimated=True),
        200,
        NOW,
    )

    assert result.basis == "estimated"


@pytest.mark.parametrize("status", (0, 400, 429, 500))
def test_failed_openai_usage_is_modelled(status: int) -> None:
    result = estimate_cost(
        "openai",
        "gpt-4o-mini",
        Usage(prompt_tokens=100, completion_tokens=25),
        status,
        NOW,
    )

    assert result.basis == "modelled"
    failed_overhead = DEFAULT_PRICING_BOOK.for_time("openai", NOW).failed_request_overhead_usd
    assert result.cost_usd == failed_overhead


def test_missing_usage_is_modelled_instead_of_treated_as_a_zero_cost_bill() -> None:
    result = estimate_cost("openai", "gpt-4o-mini", None, 200, NOW)
    empty_usage = estimate_cost("openai", "gpt-4o-mini", {}, 200, NOW)

    assert result.basis == "modelled"
    assert result.cost_usd == DEFAULT_PRICING_BOOK.for_time("openai", NOW).per_request_overhead_usd
    assert empty_usage.basis == "modelled"


def test_stripe_is_always_modelled_and_aws_is_unsupported() -> None:
    stripe = estimate_cost("stripe", None, Usage(), 200, NOW)
    aws = estimate_cost("aws", None, Usage(), 200, NOW)

    assert stripe.basis == "modelled"
    assert stripe.cost_usd == Decimal("0.00040000")
    assert aws.basis == "modelled"
    assert aws.cost_usd == 0
    assert aws.supported is False


def test_invalid_pricing_currency_and_missing_provider_file_fail_fast(tmp_path: Path) -> None:
    source = json.loads((PRICING_FILES / "openai" / "2026-01-15.json").read_text(encoding="utf-8"))
    provider_dir = tmp_path / "openai"
    provider_dir.mkdir()
    (provider_dir / "2026-01-15.json").write_text(
        json.dumps(dict(source, currency="INR")), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="Invalid pricing file"):
        PricingBook.from_directory(tmp_path, providers=("openai",))
    with pytest.raises(RuntimeError, match="Missing pricing directory"):
        PricingBook.from_directory(tmp_path, providers=("stripe",))


def test_invalid_pricing_json_fails_at_book_load(tmp_path: Path) -> None:
    provider_dir = tmp_path / "openai"
    provider_dir.mkdir()
    (provider_dir / "broken.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Could not load pricing file"):
        PricingBook.from_directory(tmp_path, providers=("openai",))


def test_large_negative_and_cached_token_counts_are_clamped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    result = estimate_cost(
        "openai",
        "gpt-4o-mini",
        Usage(
            prompt_tokens=-10,
            completion_tokens=1_000_000_001,
            cached_prompt_tokens=20,
        ),
        200,
        NOW,
    )

    assert result.cost_usd >= 0
    assert "Negative token count clamped" in caplog.text
    assert "Excessive token count clamped" in caplog.text
    assert "Cached token count exceeded prompt" in caplog.text
