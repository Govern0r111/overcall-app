import statistics

from ..pricing_config import PRICING
from .base import PROVIDER_LABEL, Finding, Rule, by_endpoint, gap_s, group_by, is_ok, severity_for

FIXES = {
    "openai": "Debounce the UI action that triggers this call and keep an in-flight map keyed by payload hash so concurrent callers share one pending response. Cache the result for a few seconds.",
    "stripe": "Send an Idempotency-Key header on every POST (Stripe dedupes server-side for 24h) and disable the submit button while the request is in flight.",
}


class DuplicateCalls(Rule):
    id = "duplicate_calls"
    name = "Duplicate calls"
    tier = 1
    description = "The exact same request (provider, method, payload hash) repeated within the short window after a successful response."

    def detect(self, logs, ctx):
        short = ctx.w.short_window_s
        flagged, gaps = [], {}
        for group in group_by(logs, lambda l: (l.provider, l.method, l.req_hash)).values():
            for prev, cur in zip(group, group[1:]):
                g = gap_s(prev, cur)
                if g <= short and is_ok(prev.status):
                    flagged.append(cur)
                    gaps[cur.id] = g
        findings = []
        for (prov, ep), items in by_endpoint(flagged).items():
            waste = {l.id: l.cost_usd for l in items}
            money_risk = (
                prov == "stripe"
                and ep in PRICING["stripe"]["money_moving_endpoints"]
                and any(not l.has_idempotency_key for l in items)
            )
            n, label = len(items), PROVIDER_LABEL.get(prov, prov)
            summary = f"{n} requests to {ep} were exact copies of a call that had just succeeded. You paid for the same answer more than once."
            if money_risk:
                summary += " These are payment writes without an Idempotency-Key, so customers may be charged twice."
            med = statistics.median(gaps[l.id] for l in items)
            findings.append(
                Finding(
                    issue_type=self.id,
                    severity="critical"
                    if money_risk
                    else severity_for(ctx.monthly(sum(waste.values()))),
                    provider=prov,
                    endpoint=ep,
                    title=f"Identical {label} calls repeated within seconds",
                    summary=summary,
                    explanation=(
                        f"Grouped by provider + method + payload hash. {n} repeats across {len({l.req_hash for l in items})} "
                        f"distinct payloads arrived ≤ {short:g}s after a 2xx response to the same hash (median gap {med:.1f}s). "
                        f"Example hash {items[0].req_hash}."
                    ),
                    suggested_fix=FIXES.get(prov, FIXES["openai"]),
                    affected=items,
                    waste_by_request=waste,
                )
            )
        return findings
