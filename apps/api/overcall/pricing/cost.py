from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from .loader import DEFAULT_PRICING_BOOK, PricingBook
from .models import CostResult, ModelPrice, PricingFile, Usage

logger = logging.getLogger(__name__)
_MILLION = Decimal("1000000")
_ZERO = Decimal("0")
_COST_QUANTUM = Decimal("0.00000001")
_MAX_TOKEN_COUNT = 1_000_000_000
_MAX_COST = Decimal("999999.99999999")


def _normalize_usage(value: Usage | dict[str, object] | None) -> Usage | None:
    if value is None:
        return None
    if isinstance(value, Usage):
        if not {"prompt_tokens", "completion_tokens"}.intersection(value.model_fields_set):
            return None
        return value
    if not {"prompt_tokens", "completion_tokens"}.intersection(value):
        return None
    return Usage.model_validate(value)


def _clamp_tokens(name: str, value: int) -> int:
    if value < 0:
        logger.warning("Negative token count clamped to zero field=%s", name)
        return 0
    if value > _MAX_TOKEN_COUNT:
        logger.warning("Excessive token count clamped field=%s max=%s", name, _MAX_TOKEN_COUNT)
        return _MAX_TOKEN_COUNT
    return value


def resolve_model(pricing: PricingFile, model: str | None) -> tuple[str | None, bool]:
    if not pricing.models:
        return None, False
    if model is None:
        return pricing.default_model, True
    if model in pricing.models:
        return model, False
    matches = [known for known in pricing.models if model.startswith(known)]
    if matches:
        return max(matches, key=len), False
    logger.info("Unknown model priced with provider default model model_length=%d", len(model))
    return pricing.default_model, True


def model_price(
    model: str | None,
    at: datetime | None = None,
    book: PricingBook = DEFAULT_PRICING_BOOK,
) -> tuple[str, ModelPrice]:
    pricing = book.for_time("openai", at or datetime.now(UTC))
    resolved, _fallback_used = resolve_model(pricing, model)
    if resolved is None:
        raise ValueError("OpenAI pricing has no default model")
    return resolved, pricing.models[resolved]


def _round_cost(amount: Decimal) -> Decimal:
    if amount > _MAX_COST:
        logger.warning("Estimated cost exceeded supported storage range; clamped")
        amount = _MAX_COST
    return max(_ZERO, amount).quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)


def estimate_cost(
    provider: str,
    model: str | None,
    usage: Usage | dict[str, object] | None,
    status: int,
    at: datetime,
    *,
    book: PricingBook = DEFAULT_PRICING_BOOK,
) -> CostResult:
    pricing = book.for_time(provider, at)
    if not pricing.supported:
        return CostResult(
            cost_usd=_ZERO,
            basis="modelled",
            pricing_version=pricing.version,
            fallback_used=False,
            supported=False,
        )

    normalized_usage = _normalize_usage(usage)
    if provider == "stripe":
        overhead = pricing.per_request_overhead_usd
        if not 200 <= status < 300:
            overhead = pricing.failed_request_overhead_usd
        return CostResult(
            cost_usd=_round_cost(overhead),
            basis="modelled",
            pricing_version=pricing.version,
            fallback_used=False,
        )

    if not 200 <= status < 300:
        return CostResult(
            cost_usd=_round_cost(pricing.failed_request_overhead_usd),
            basis="modelled",
            pricing_version=pricing.version,
            fallback_used=False,
        )
    if normalized_usage is None:
        return CostResult(
            cost_usd=_round_cost(pricing.per_request_overhead_usd),
            basis="modelled",
            pricing_version=pricing.version,
            fallback_used=False,
        )

    resolved, fallback_used = resolve_model(pricing, model)
    if resolved is None:
        return CostResult(
            cost_usd=_ZERO,
            basis="modelled",
            pricing_version=pricing.version,
            fallback_used=False,
            supported=False,
        )

    prompt_tokens = _clamp_tokens("prompt_tokens", normalized_usage.prompt_tokens)
    completion_tokens = _clamp_tokens("completion_tokens", normalized_usage.completion_tokens)
    cached_tokens = _clamp_tokens("cached_prompt_tokens", normalized_usage.cached_prompt_tokens)
    if cached_tokens > prompt_tokens:
        logger.warning("Cached token count exceeded prompt; clamped to prompt token count")
        cached_tokens = prompt_tokens
    prices = pricing.models[resolved]
    standard_input = Decimal(prompt_tokens - cached_tokens) * prices.input_per_1m
    cached_input = Decimal(cached_tokens) * prices.cached_input_per_1m
    output = Decimal(completion_tokens) * prices.output_per_1m
    amount = _round_cost((standard_input + cached_input + output) / _MILLION)
    basis = "estimated" if normalized_usage.tokens_estimated or fallback_used else "billed"
    return CostResult(
        cost_usd=amount,
        basis=basis,
        pricing_version=pricing.version,
        fallback_used=fallback_used,
    )
