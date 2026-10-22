from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ...pricing import DEFAULT_PRICING_BOOK
from ...pricing.cost import resolve_model
from ..base import Finding, LogRow, RuleContext, is_success, ordered_logs
from ..savings import clamp_waste
from .common import group_by, monthly_rule_severity

FIX = (
    "Keep the long, unchanging part of the prompt identical and first so provider prompt "
    "caching applies, send it once per session where possible, and trim old turns that no "
    "longer matter."
)
MILLION = Decimal("1000000")


class TokenBloat:
    id = "token_bloat"
    name = "Token bloat"
    tier = 3
    description = (
        "The same long conversation context sent again and again at full input price. Experimental."
    )
    default_enabled = False
    threshold_keys = ("token_bloat_min_repeats", "token_bloat_min_context_tokens")

    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]:
        min_repeats = int(ctx.thresholds.token_bloat_min_repeats)
        min_tokens = int(ctx.thresholds.token_bloat_min_context_tokens)

        candidates: list[LogRow] = []
        prices = {}
        for row in ordered_logs(logs):
            if (
                row.provider != "openai"
                or not is_success(row.status)
                or row.context_hash is None
                or row.context_tokens is None
                or row.context_tokens < min_tokens
            ):
                continue
            pricing = DEFAULT_PRICING_BOOK.for_time("openai", row.occurred_at)
            if row.endpoint not in pricing.chat_endpoints or row.model is None:
                continue
            resolved, fallback = resolve_model(pricing, row.model)
            if resolved is None or fallback:
                continue
            prices[row.id] = pricing.models[resolved]
            candidates.append(row)

        groups = group_by(candidates, lambda row: (row.endpoint, row.context_hash))
        repeats_by_endpoint: dict[str, list[LogRow]] = {}
        repeat_counts: dict[str, list[int]] = {}
        for (endpoint, _context), rows in groups.items():
            if len(rows) < min_repeats:
                continue
            repeats_by_endpoint.setdefault(endpoint, []).extend(rows[1:])
            repeat_counts.setdefault(endpoint, []).append(len(rows) - 1)

        findings = []
        for endpoint, repeats in sorted(repeats_by_endpoint.items()):
            repeats.sort(key=lambda row: (row.occurred_at, row.id))
            waste = {}
            for row in repeats:
                price = prices[row.id]
                uncached_gap = price.input_per_1m - price.cached_input_per_1m
                tokens = Decimal(row.context_tokens or 0)
                waste[row.id] = clamp_waste(tokens * uncached_gap / MILLION, row.cost_usd)
            counts = repeat_counts[endpoint]
            average_repeats = sum(counts) / len(counts)
            findings.append(
                Finding(
                    rule_id=self.id,
                    tier=3,
                    experimental=True,
                    confidence=round(min(0.85, 0.45 + 0.05 * average_repeats), 2),
                    severity=monthly_rule_severity(
                        sum(waste.values(), Decimal("0")), ctx.window_days, self.id
                    ),
                    provider="openai",
                    endpoint=endpoint,
                    title="Same long context sent repeatedly",
                    summary=(
                        f"{len(repeats)} repeat sends of a context of at least {min_tokens:,} "
                        f"tokens across {len(counts)} distinct context(s)."
                    ),
                    explanation=(
                        "Contexts are compared by a hash, so the content itself is never "
                        "stored. The estimate is the difference between the standard and "
                        "cached input price on the repeated context tokens. This rule is "
                        "experimental: some repetition is intentional."
                    ),
                    suggested_fix=FIX,
                    affected=repeats,
                    waste_by_request=waste,
                )
            )
        return findings
