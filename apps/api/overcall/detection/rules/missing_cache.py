from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..base import Finding, LogRow, RuleContext, is_success, ordered_logs
from .common import (
    cacheable,
    cost_by_request,
    gap_seconds,
    group_by,
    monthly_rule_severity,
    provider_label,
)

OPENAI_FIX = (
    "Cache deterministic responses by request hash. For embeddings, reuse the existing vector "
    "when the input has not changed."
)
STRIPE_FIX = (
    "Cache unchanged GET results briefly and invalidate them from Stripe webhooks when the "
    "underlying resource changes."
)


class MissingCache:
    id = "missing_cache"
    name = "Missing cache"
    tier = 1
    description = (
        "An identical GET or documented deterministic POST repeated after the short window and "
        "within the long window following a successful response."
    )
    default_enabled = True
    threshold_keys = ("short_window_s", "long_window_s")

    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]:
        short_window = ctx.thresholds.short_window_s
        long_window = ctx.thresholds.long_window_s
        candidates = [row for row in ordered_logs(logs) if cacheable(row)]
        groups = group_by(
            candidates,
            lambda row: (row.provider, row.method, row.req_hash),
        )
        repeats: dict[tuple[str, str], list[LogRow]] = {}
        for group in groups.values():
            for previous, current in zip(group, group[1:], strict=False):
                gap = gap_seconds(previous, current)
                if gap > short_window and gap <= long_window and is_success(previous.status):
                    repeats.setdefault((current.provider, current.endpoint), []).append(current)

        findings = []
        for (provider, endpoint), affected in sorted(repeats.items()):
            waste = cost_by_request(affected)
            total = sum(waste.values())
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=monthly_rule_severity(total, ctx.window_days, self.id),
                    provider=provider,
                    endpoint=endpoint,
                    title=f"Unchanged {provider_label(provider)} data fetched again",
                    summary=(
                        f"{len(affected)} identical requests to {endpoint} repeated after the "
                        "short window. A brief cache can avoid unnecessary calls."
                    ),
                    explanation=(
                        f"An identical GET or deterministic POST arrived more than "
                        f"{short_window:g}s and no more than {long_window:g}s after a successful "
                        "response. The response contents are not stored, so a change between "
                        "requests cannot be ruled out."
                    ),
                    suggested_fix=STRIPE_FIX if provider == "stripe" else OPENAI_FIX,
                    affected=affected,
                    waste_by_request=waste,
                    critical_at=Decimal("40"),
                    warning_at=Decimal("1"),
                )
            )
        return findings
