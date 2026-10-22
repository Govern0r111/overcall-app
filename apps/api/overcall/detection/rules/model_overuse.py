from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ...pricing import DEFAULT_PRICING_BOOK
from ...pricing.cost import resolve_model
from ...pricing.models import ModelPrice
from ..base import Finding, LogRow, RuleContext, is_success, ordered_logs
from ..savings import clamp_waste
from .common import group_by, monthly_rule_severity

MILLION = Decimal("1000000")
FIX = (
    "Route short, simple tasks such as classification, extraction or tagging to the smaller "
    "model and keep the larger one for work that needs it. Test quality on a sample first."
)


def _cost(price: ModelPrice, row: LogRow) -> Decimal:
    cached = min(row.cached_prompt_tokens, row.prompt_tokens)
    return (
        Decimal(row.prompt_tokens - cached) * price.input_per_1m
        + Decimal(cached) * price.cached_input_per_1m
        + Decimal(row.completion_tokens) * price.output_per_1m
    ) / MILLION


class ModelOveruse:
    id = "model_overuse"
    name = "Model overuse"
    tier = 3
    description = (
        "A premium model used for small tasks where its cheaper sibling may do. Experimental."
    )
    default_enabled = False
    threshold_keys = (
        "model_overuse_max_prompt_tokens",
        "model_overuse_max_completion_tokens",
        "model_overuse_min_calls",
    )

    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]:
        max_prompt = int(ctx.thresholds.model_overuse_max_prompt_tokens)
        max_completion = int(ctx.thresholds.model_overuse_max_completion_tokens)
        min_calls = int(ctx.thresholds.model_overuse_min_calls)

        candidates: list[tuple[LogRow, str, str, ModelPrice, ModelPrice]] = []
        for row in ordered_logs(logs):
            if (
                row.provider != "openai"
                or not is_success(row.status)
                or row.model is None
                or row.uses_tools
                or row.prompt_tokens > max_prompt
                or row.completion_tokens > max_completion
            ):
                continue
            pricing = DEFAULT_PRICING_BOOK.for_time("openai", row.occurred_at)
            if row.endpoint not in pricing.chat_endpoints:
                continue
            resolved, fallback = resolve_model(pricing, row.model)
            if resolved is None or fallback:
                continue
            target = pricing.downgrade_map.get(resolved)
            if target is None or pricing.models[resolved].tier != "high":
                continue
            candidates.append(
                (row, resolved, target, pricing.models[resolved], pricing.models[target])
            )

        groups = group_by(candidates, lambda item: (item[0].endpoint, item[1], item[2]))
        findings = []
        for (endpoint, model, target), items in sorted(groups.items()):
            if len(items) < min_calls:
                continue
            rows = [item[0] for item in items]
            waste = {
                row.id: clamp_waste(_cost(current, row) - _cost(cheaper, row), row.cost_usd)
                for row, _model, _target, current, cheaper in items
            }
            average_completion = sum(row.completion_tokens for row in rows) / len(rows)
            findings.append(
                Finding(
                    rule_id=self.id,
                    tier=3,
                    experimental=True,
                    confidence=0.7 if average_completion < 60 else 0.55,
                    severity=monthly_rule_severity(
                        sum(waste.values(), Decimal("0")), ctx.window_days, self.id
                    ),
                    provider="openai",
                    endpoint=endpoint,
                    title=f"{model} used for small tasks",
                    summary=(
                        f"{len(rows)} calls to {model} had prompts of at most {max_prompt:,} "
                        f"tokens and replies of at most {max_completion:,} tokens, without "
                        f"tools. {target} may be enough."
                    ),
                    explanation=(
                        "The saving is the price difference between the two models at the same "
                        "token counts. Only sizes are known, so task difficulty cannot be "
                        "judged; this rule is experimental."
                    ),
                    suggested_fix=FIX,
                    affected=rows,
                    waste_by_request=waste,
                )
            )
        return findings
