from ..pricing_config import PRICING, model_price
from .base import Finding, Rule, group_by, is_ok, severity_for


class TokenBloat(Rule):
    id = "token_bloat"
    name = "Repeated context resends"
    tier = 3
    description = "Chat requests that resend the same large system/context block on every call (LLM-specific, experimental)."

    def detect(self, logs, ctx):
        w = ctx.w
        chat = PRICING["openai"]["chat_endpoints"]
        cands = [
            l
            for l in logs
            if l.provider == "openai"
            and l.endpoint in chat
            and l.context_hash
            and is_ok(l.status)
            and l.prompt_tokens >= w.token_bloat_min_prompt_tokens
        ]
        groups = [
            g
            for g in group_by(cands, lambda l: l.context_hash).values()
            if len(g) >= w.token_bloat_min_repeats
        ]
        if not groups:
            return []
        items, waste = [], {}
        for g in groups:
            for l in g[1:]:
                _, p = model_price(l.model)
                items.append(l)
                waste[l.id] = l.prompt_tokens * (p["input_per_1m"] - p["cached_input_per_1m"]) / 1e6
        avg_repeats = sum(len(g) for g in groups) / len(groups)
        avg_pt = sum(l.prompt_tokens for l in items) / len(items)
        return [
            Finding(
                issue_type=self.id,
                severity=severity_for(
                    ctx.monthly(sum(waste.values())), critical_at=30.0, warning_at=1.0
                ),
                provider="openai",
                endpoint=chat[0],
                title="Same long context resent on every call",
                summary=f"{len(items)} chat requests re-sent the same large block of context (~{avg_pt:,.0f} tokens each). Prompt caching or a shorter summary could cut this input cost.",
                explanation=(
                    f"Grouped by a hash of system/developer messages. {len(groups)} contexts were resent ≥{w.token_bloat_min_repeats} times "
                    f"with ≥{w.token_bloat_min_prompt_tokens} prompt tokens (avg {avg_repeats:.1f} sends each). "
                    "Savings assume cached-input pricing on the repeated calls."
                ),
                suggested_fix="Keep the stable context at the start of the prompt so OpenAI's automatic prompt caching applies, or store a condensed summary and send that instead of the full document each turn.",
                affected=items,
                waste_by_request=waste,
                confidence=round(min(0.85, 0.45 + 0.05 * avg_repeats), 2),
            )
        ]
