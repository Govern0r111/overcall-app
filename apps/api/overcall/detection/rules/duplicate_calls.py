from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from statistics import median

from ..base import Finding, LogRow, RuleContext, is_success, ordered_logs
from .common import (
    cost_by_request,
    gap_seconds,
    group_by,
    money_moving_endpoint,
    monthly_rule_severity,
    provider_label,
)

OPENAI_FIX = (
    "Debounce the action that triggers this request and share an in-flight result for identical "
    "payloads. If repeat calls are intentional polling, slow them down or use a webhook."
)
STRIPE_FIX = (
    "Send an Idempotency-Key on every payment write and prevent a second submit while the first "
    "request is in flight."
)


class DuplicateCalls:
    id = "duplicate_calls"
    name = "Duplicate calls"
    tier = 1
    description = (
        "The same provider, method, and request hash repeated within the short window after a "
        "successful response."
    )
    default_enabled = True
    threshold_keys = ("short_window_s",)

    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]:
        short_window = ctx.thresholds.short_window_s
        groups = group_by(
            ordered_logs(logs),
            lambda row: (row.provider, row.method, row.req_hash),
        )
        repeats: dict[tuple[str, str], list[LogRow]] = {}
        gaps: dict[object, float] = {}
        risky_ids: set = set()

        for group in groups.values():
            for previous, current in zip(group, group[1:], strict=False):
                gap = gap_seconds(previous, current)
                if gap < 0 or gap > short_window or not is_success(previous.status):
                    continue
                key = (current.provider, current.endpoint)
                repeats.setdefault(key, []).append(current)
                gaps[current.id] = gap
                if money_moving_endpoint(current) and not current.has_idempotency_key:
                    risky_ids.add(current.id)

        findings = []
        for (provider, endpoint), affected in sorted(repeats.items()):
            waste = cost_by_request(affected)
            risky = any(row.id in risky_ids for row in affected)
            total = sum(waste.values())
            gaps_for_group = [gaps[row.id] for row in affected]
            summary = (
                f"{len(affected)} requests to {endpoint} repeated a call that had just succeeded. "
                "If this is intentional polling, slow it down or use webhooks."
            )
            if risky:
                summary += (
                    " A payment write without an Idempotency-Key can charge or create a payment "
                    "twice."
                )
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=(
                        "critical"
                        if risky
                        else monthly_rule_severity(total, ctx.window_days, self.id)
                    ),
                    provider=provider,
                    endpoint=endpoint,
                    title=f"Identical {provider_label(provider)} calls repeated within seconds",
                    summary=summary,
                    explanation=(
                        "Grouped by provider, method, and request hash. Identical requests "
                        "arrived "
                        f"within {short_window:g}s after a 2xx response; the median gap was "
                        f"{median(gaps_for_group):.2f}s."
                    ),
                    suggested_fix=STRIPE_FIX if provider == "stripe" else OPENAI_FIX,
                    affected=affected,
                    waste_by_request=waste,
                    critical_at=Decimal("20"),
                    warning_at=Decimal("2"),
                    _money_risk=risky,
                )
            )
        return findings
