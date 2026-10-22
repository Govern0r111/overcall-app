from ..pricing_config import PRICING, estimate_cost, model_price
from .base import Finding, Rule, group_by, is_ok, severity_for

MIN_CALLS = 10


class ModelOveruse(Rule):
    id = "model_overuse"
    name = "High-cost model for small tasks"
    tier = 3
    description = "Premium models used for short prompts with short answers where a smaller model is usually sufficient (experimental)."

    def detect(self, logs, ctx):
        w, cfg = ctx.w, PRICING["openai"]
        cands = []
        for l in logs:
            if (
                l.provider != "openai"
                or l.endpoint not in cfg["chat_endpoints"]
                or not is_ok(l.status)
            ):
                continue
            key, p = model_price(l.model)
            if (
                p["tier"] == "high"
                and key in cfg["downgrade_map"]
                and l.prompt_tokens <= w.model_overuse_max_prompt_tokens
                and l.completion_tokens <= w.model_overuse_max_completion_tokens
            ):
                cands.append(l)
        findings = []
        for model, items in group_by(cands, lambda l: model_price(l.model)[0]).items():
            if len(items) < MIN_CALLS:
                continue
            target = cfg["downgrade_map"][model]
            waste = {
                l.id: max(
                    0.0,
                    l.cost_usd
                    - estimate_cost("openai", target, l.prompt_tokens, l.completion_tokens),
                )
                for l in items
            }
            avg_pt = sum(l.prompt_tokens for l in items) / len(items)
            avg_ct = sum(l.completion_tokens for l in items) / len(items)
            findings.append(
                Finding(
                    issue_type=self.id,
                    severity=severity_for(
                        ctx.monthly(sum(waste.values())), critical_at=30.0, warning_at=1.0
                    ),
                    provider="openai",
                    endpoint=cfg["chat_endpoints"][0],
                    title="Premium model used for small tasks",
                    summary=f"{len(items)} short requests (≈{avg_pt:.0f} tokens in, {avg_ct:.0f} out) went to {model}. A smaller model like {target} usually handles tasks this size for a fraction of the cost.",
                    explanation=(
                        f"{model} calls with ≤{w.model_overuse_max_prompt_tokens} prompt and ≤{w.model_overuse_max_completion_tokens} "
                        f"completion tokens. Savings = price difference vs {target} at identical token counts. "
                        "Output quality is not measured — validate on a sample first."
                    ),
                    suggested_fix=f"Route short classification/extraction prompts to {target} and keep {model} for long or reasoning-heavy requests. Compare outputs on ~100 real inputs before switching.",
                    affected=items,
                    waste_by_request=waste,
                    confidence=0.7 if avg_ct < 60 else 0.55,
                )
            )
        return findings
