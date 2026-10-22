from ..pricing_config import PRICING
from .base import PROVIDER_LABEL, Finding, Rule, by_endpoint, gap_s, group_by, is_ok, severity_for

FIXES = {
    "openai": "Store results keyed by a hash of the input (identical inputs always return the same embedding / list). An in-memory LRU or Redis with a TTL of a few minutes is enough.",
    "stripe": "Cache responses keyed by the request URL with a TTL of a few minutes, and refresh the cache from Stripe webhooks (customer.updated, etc.) instead of polling.",
}


def cacheable(l) -> bool:
    return l.method == "GET" or l.endpoint in PRICING.get(l.provider, {}).get("deterministic_post_endpoints", [])


class MissingCache(Rule):
    id = "missing_cache"
    name = "Missing caching"
    tier = 1
    description = "Idempotent requests (GET or deterministic POST) with identical payloads re-sent within the long window after a successful response."

    def detect(self, logs, ctx):
        short, long_ = ctx.w.short_window_s, ctx.w.long_window_s
        flagged = []
        candidates = [l for l in logs if cacheable(l)]
        for group in group_by(candidates, lambda l: (l.provider, l.method, l.req_hash)).values():
            for prev, cur in zip(group, group[1:]):
                if short < gap_s(prev, cur) <= long_ and is_ok(prev.status):
                    flagged.append(cur)
        findings = []
        for (prov, ep), items in by_endpoint(flagged).items():
            waste = {l.id: l.cost_usd for l in items}
            n, distinct = len(items), len({l.req_hash for l in items})
            kind = "GET" if items[0].method == "GET" else "deterministic POST"
            findings.append(Finding(
                issue_type=self.id,
                severity=severity_for(ctx.monthly(sum(waste.values())), critical_at=40.0, warning_at=1.0),
                provider=prov, endpoint=ep,
                title=f"Unchanged {PROVIDER_LABEL.get(prov, prov)} data fetched again and again",
                summary=f"{n} calls to {ep} asked for data your app had already received minutes earlier. A short cache would answer these for free.",
                explanation=(
                    f"Idempotent {kind} with an identical payload hash repeated {short:g}s–{long_:g}s after a successful response. "
                    f"{distinct} distinct resources, {n / distinct:.1f} re-fetches each on average."
                ),
                suggested_fix=FIXES.get(prov, FIXES["stripe"]),
                affected=items, waste_by_request=waste,
            ))
        return findings
