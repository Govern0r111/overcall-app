import statistics

from .base import PROVIDER_LABEL, Finding, Rule, by_endpoint, severity_for

FIXES = {
    "openai": "Send only the relevant chunks (retrieve the top-k passages) instead of whole documents, and summarize long histories before resending them.",
    "stripe": "Use smaller pages (limit=10–25) with starting_after, and drop expand[] on list calls unless you really need the nested objects.",
}


class OversizedPayload(Rule):
    id = "oversized_payload"
    name = "Oversized payloads"
    tier = 2
    description = "Request or response bodies larger than the size threshold (large prompts, unpaginated or over-expanded lists)."

    def detect(self, logs, ctx):
        limit = ctx.w.oversized_bytes
        flagged = [l for l in logs if max(l.req_size, l.resp_size) > limit]
        findings = []
        for (prov, ep), items in by_endpoint(flagged).items():
            waste = {}
            for l in items:
                size = max(l.req_size, l.resp_size)
                waste[l.id] = l.cost_usd * (size - limit) / size
            sizes = [max(l.req_size, l.resp_size) / 1000 for l in items]
            n = len(items)
            if prov == "openai":
                summary = f"{n} requests to {ep} sent far more text than usual (up to {max(sizes):.0f} KB). You're billed for every token, even the ones the model doesn't need."
            else:
                summary = f"{n} responses from {ep} returned up to {max(sizes):.0f} KB each. Fetching less per page is faster and cheaper to process."
            findings.append(
                Finding(
                    issue_type=self.id,
                    severity=severity_for(
                        ctx.monthly(sum(waste.values())), critical_at=30.0, warning_at=1.0
                    ),
                    provider=prov,
                    endpoint=ep,
                    title=f"Very large {PROVIDER_LABEL.get(prov, prov)} payloads",
                    summary=summary,
                    explanation=(
                        f"Request or response body exceeded the {limit / 1000:.0f} KB threshold (tunable in Settings). "
                        f"Median size {statistics.median(sizes):.0f} KB. Savings assume trimming each payload down to the threshold."
                    ),
                    suggested_fix=FIXES.get(prov, FIXES["stripe"]),
                    affected=items,
                    waste_by_request=waste,
                )
            )
        return findings
