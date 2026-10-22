from ..pricing_config import PRICING
from .base import PROVIDER_LABEL, Finding, Rule, by_endpoint, gap_s, group_by, severity_for


def batch_for(l):
    return PRICING.get(l.provider, {}).get("batch_equivalents", {}).get(f"{l.method} {l.endpoint}")


def bursts(group, window_s, min_calls):
    out, cur = [], [group[0]]
    for prev, nxt in zip(group, group[1:]):
        if gap_s(prev, nxt) <= window_s:
            cur.append(nxt)
        else:
            if len(cur) >= min_calls:
                out.append(cur)
            cur = [nxt]
    if len(cur) >= min_calls:
        out.append(cur)
    return out


class UnbatchedCalls(Rule):
    id = "unbatched_calls"
    name = "Unbatched calls"
    tier = 2
    description = "Bursts of single calls to an endpoint that has a documented batch equivalent."

    def detect(self, logs, ctx):
        w = ctx.w
        candidates = [l for l in logs if batch_for(l)]
        found, meta = [], {}
        for key, group in group_by(candidates, lambda l: (l.provider, l.method, l.endpoint, l.caller)).items():
            for b in bursts(group, w.unbatched_window_s, w.unbatched_min_calls):
                found += b[1:]
                m = meta.setdefault((key[0], key[2]), {"bursts": 0, "largest": 0, "callers": set()})
                m["bursts"] += 1
                m["largest"] = max(m["largest"], len(b))
                m["callers"].add(key[3] or "unknown")
        findings = []
        for (prov, ep), items in by_endpoint(found).items():
            batch = batch_for(items[0])
            waste = {l.id: l.cost_usd * batch["discount"] for l in items}
            m, label = meta[(prov, ep)], PROVIDER_LABEL.get(prov, prov)
            findings.append(Finding(
                issue_type=self.id,
                severity=severity_for(ctx.monthly(sum(waste.values())), critical_at=30.0, warning_at=1.0),
                provider=prov, endpoint=ep,
                title=f"Many single {label} calls that could be batched",
                summary=f"Your app made {len(items)} one-at-a-time calls to {ep} in quick bursts. {label} offers a batch option that does the same work in fewer, cheaper requests.",
                explanation=(
                    f"Bursts of ≥{w.unbatched_min_calls} calls with ≤{w.unbatched_window_s:g}s between them "
                    f"({m['bursts']} bursts, largest {m['largest']} calls; caller: {', '.join(sorted(m['callers']))}). "
                    f"Documented batch equivalent: {batch['method']}."
                ),
                suggested_fix=batch["fix"], affected=items, waste_by_request=waste,
            ))
        return findings
