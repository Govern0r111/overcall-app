"""Compatibility surface for existing detection rules during their planned migration."""

from __future__ import annotations

from datetime import UTC, datetime

from .pricing import DEFAULT_PRICING_BOOK, Usage
from .pricing import estimate_cost as calculate_cost
from .pricing.cost import resolve_model
from .pricing.loader import PROVIDERS

_DEFAULT_AT = datetime.now(UTC)


def _legacy_view(provider: str) -> dict:
    pricing = DEFAULT_PRICING_BOOK.for_time(provider, _DEFAULT_AT)
    data = dict(pricing.legacy)
    data.update(
        {
            "provider": pricing.provider,
            "version": pricing.version,
            "effective_from": pricing.effective_from.isoformat(),
            "retrieved_at": pricing.retrieved_at.isoformat(),
            "source_url": pricing.source_url,
            "currency": pricing.currency,
            "models": {
                model_name: {
                    **{
                        key: float(value)
                        for key, value in model.model_dump().items()
                        if key != "tier"
                    },
                    "tier": model.tier,
                }
                for model_name, model in pricing.models.items()
            },
            "default_model": pricing.default_model,
            "per_request_overhead_usd": float(pricing.per_request_overhead_usd),
            "failed_request_overhead_usd": float(pricing.failed_request_overhead_usd),
            "chat_endpoints": list(pricing.chat_endpoints),
            "deterministic_post_endpoints": list(pricing.deterministic_post_endpoints),
            "downgrade_map": dict(pricing.downgrade_map),
            "batch_equivalents": {
                endpoint: {
                    **equivalent.model_dump(exclude={"discount"}),
                    "discount": float(equivalent.discount),
                }
                for endpoint, equivalent in pricing.batch_equivalents.items()
            },
            "supported": pricing.supported,
        }
    )
    return data


PRICING = {provider: _legacy_view(provider) for provider in PROVIDERS}


def model_price(model: str | None) -> tuple[str, dict]:
    pricing = DEFAULT_PRICING_BOOK.for_time("openai", _DEFAULT_AT)
    resolved, _fallback_used = resolve_model(pricing, model)
    if resolved is None:
        raise ValueError("OpenAI pricing has no default model")
    return resolved, PRICING["openai"]["models"][resolved]


def is_ok(status: int) -> bool:
    return 200 <= status < 300


def estimate_cost(
    provider: str,
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    status: int = 200,
) -> float:
    result = calculate_cost(
        provider=provider,
        model=model,
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
        status=status,
        at=datetime.now(UTC),
    )
    return float(result.cost_usd)
