from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..base import Finding, LogRow, RuleContext, ordered_logs
from ..savings import clamp_waste
from .common import group_by, monthly_rule_severity, provider_label

OPENAI_FIX = (
    "Trim what you send: drop unused fields and old conversation turns, and summarise or "
    "retrieve only the relevant parts of large documents instead of sending them whole."
)
STRIPE_FIX = (
    "Request fewer objects per call with a smaller limit, filters or pagination, and avoid "
    "expanding fields you do not use."
)


def payload_size(row: LogRow) -> int:
    return max(row.req_size, row.resp_size)


class OversizedPayload:
    id = "oversized_payload"
    name = "Oversized payloads"
    tier = 2
    description = (
        "Requests or responses larger than the configured size limit, which usually means more "
        "data is being sent or fetched than needed."
    )
    default_enabled = True
    threshold_keys = ("oversized_bytes",)

    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]:
        limit = int(ctx.thresholds.oversized_bytes)
        oversized = [row for row in ordered_logs(logs) if payload_size(row) > limit]
        findings = []
        for (provider, endpoint), affected in sorted(
            group_by(oversized, lambda row: (row.provider, row.endpoint)).items()
        ):
            waste = {
                row.id: clamp_waste(
                    row.cost_usd * Decimal(payload_size(row) - limit) / Decimal(payload_size(row)),
                    row.cost_usd,
                )
                for row in affected
            }
            largest = max(payload_size(row) for row in affected)
            findings.append(
                Finding(
                    rule_id=self.id,
                    tier=2,
                    severity=monthly_rule_severity(
                        sum(waste.values(), Decimal("0")), ctx.window_days, self.id
                    ),
                    provider=provider,
                    endpoint=endpoint,
                    title=f"Very large {provider_label(provider)} payloads",
                    summary=(
                        f"{len(affected)} requests to {endpoint} moved more than {limit:,} bytes "
                        f"(largest {largest:,} bytes)."
                    ),
                    explanation=(
                        "The larger of the request and response size exceeded the configured "
                        f"limit of {limit:,} bytes. The saving is the share of each call's cost "
                        "that sits above that limit; only sizes are recorded, never contents."
                    ),
                    suggested_fix=STRIPE_FIX if provider == "stripe" else OPENAI_FIX,
                    affected=affected,
                    waste_by_request=waste,
                )
            )
        return findings
