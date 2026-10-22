from .base import PROVIDER_LABEL, Finding, Rule, gap_s, group_by, is_ok, severity_for

FIX = (
    "Retry with exponential backoff and jitter (for example 0.5s, 1s, 2s, 4s, capped at 5 attempts) and honor the "
    "Retry-After header on 429 responses. The official OpenAI and Stripe SDKs do this for you when max_retries is set."
)


def find_chains(group, backoff_ms, min_attempts):
    chains, i = [], 0
    while i < len(group):
        chain, j = [group[i]], i
        while j + 1 < len(group) and not is_ok(group[j].status) and gap_s(group[j], group[j + 1]) * 1000 < backoff_ms:
            chain.append(group[j + 1])
            j += 1
        if len(chain) >= min_attempts:
            chains.append(chain)
        i = j + 1
    return chains


class RetryStorm(Rule):
    id = "retry_storm"
    name = "Retry storms"
    tier = 1
    description = "Repeated identical calls after a non-2xx response, retried faster than the minimum backoff."

    def detect(self, logs, ctx):
        w = ctx.w
        chains = []
        for group in group_by(logs, lambda l: (l.provider, l.method, l.req_hash)).values():
            chains += find_chains(group, w.retry_min_backoff_ms, w.retry_min_attempts)
        findings = []
        for (prov, ep), ch in group_by(chains, lambda c: (c[0].provider, c[0].endpoint)).items():
            items = [l for c in ch for l in c[1:]]
            waste = {l.id: l.cost_usd for l in items}
            codes = sorted({str(l.status) for c in ch for l in c if not is_ok(l.status)})
            n = len(items)
            sev = "critical" if n >= 30 else max(
                "warning", severity_for(ctx.monthly(sum(waste.values()))), key=["info", "warning", "critical"].index
            )
            findings.append(Finding(
                issue_type=self.id, severity=sev, provider=prov, endpoint=ep,
                title=f"Rapid retries after {PROVIDER_LABEL.get(prov, prov)} errors",
                summary=(
                    f"When {ep} failed, your app retried {n} times with almost no pause ({len(ch)} bursts). "
                    "This hammers the rate limit and usually makes the outage last longer."
                ),
                explanation=(
                    f"Chains of ≥{w.retry_min_attempts} attempts with identical payload hash where each retry followed a non-2xx "
                    f"response in < {w.retry_min_backoff_ms:g}ms. Status codes seen: {', '.join(codes)}. "
                    f"Longest chain: {max(len(c) for c in ch)} attempts."
                ),
                suggested_fix=FIX, affected=items, waste_by_request=waste,
            ))
        return findings
