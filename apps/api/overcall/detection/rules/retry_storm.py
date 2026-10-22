from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from ..base import Finding, LogRow, RuleContext, is_success, ordered_logs
from .common import cost_by_request, gap_seconds, group_by, monthly_rule_severity, provider_label

FIX = (
    "Use exponential backoff with jitter, cap the number of retries, and honor Retry-After on "
    "rate-limit responses. The provider SDK retry settings can handle this for you."
)


def retry_chains(
    group: list[LogRow],
    minimum_gap_ms: float,
    minimum_attempts: int,
) -> list[list[LogRow]]:
    chains: list[list[LogRow]] = []
    index = 0
    while index < len(group):
        chain = [group[index]]
        cursor = index
        while cursor + 1 < len(group):
            previous, current = group[cursor], group[cursor + 1]
            gap_ms = gap_seconds(previous, current) * 1000
            if is_success(previous.status) or gap_ms < 0 or gap_ms >= minimum_gap_ms:
                break
            chain.append(current)
            cursor += 1
        if len(chain) >= minimum_attempts:
            chains.append(chain)
            index = cursor + 1
        else:
            index += 1
    return chains


class RetryStorm:
    id = "retry_storm"
    name = "Retry storms"
    tier = 1
    description = (
        "Identical calls retried too quickly after non-success responses, forming a chain of "
        "multiple attempts."
    )
    default_enabled = True
    threshold_keys = ("retry_min_backoff_ms", "retry_min_attempts")

    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]:
        groups = group_by(
            ordered_logs(logs),
            lambda row: (row.provider, row.method, row.endpoint, row.req_hash),
        )
        chains = [
            chain
            for group in groups.values()
            for chain in retry_chains(
                group,
                ctx.thresholds.retry_min_backoff_ms,
                ctx.thresholds.retry_min_attempts,
            )
        ]
        by_provider_endpoint: dict[tuple[str, str], list[list[LogRow]]] = {}
        for chain in chains:
            by_provider_endpoint.setdefault((chain[0].provider, chain[0].endpoint), []).append(
                chain
            )

        findings = []
        for (provider, endpoint), endpoint_chains in sorted(by_provider_endpoint.items()):
            retries = [row for chain in endpoint_chains for row in chain[1:]]
            waste = cost_by_request(retries)
            total = sum(waste.values(), Decimal("0"))
            severity = monthly_rule_severity(total, ctx.window_days, self.id)
            if len(retries) >= 30:
                severity = "critical"
            elif severity == "info":
                severity = "warning"
            codes = sorted(
                {
                    row.status
                    for chain in endpoint_chains
                    for row in chain
                    if not is_success(row.status)
                }
            )
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=severity,
                    provider=provider,
                    endpoint=endpoint,
                    title=f"Rapid retries after {provider_label(provider)} errors",
                    summary=(
                        f"{len(retries)} retries to {endpoint} followed failed calls with too "
                        "little delay. This can worsen rate limits and outages."
                    ),
                    explanation=(
                        f"Found {len(endpoint_chains)} chain(s) of at least "
                        f"{ctx.thresholds.retry_min_attempts} identical attempts. Each retry "
                        f"followed a non-2xx response in less than "
                        f"{ctx.thresholds.retry_min_backoff_ms:g}ms. Failure statuses: "
                        f"{', '.join(map(str, codes)) or 'none'}."
                    ),
                    suggested_fix=FIX,
                    affected=retries,
                    waste_by_request=waste,
                    minimum_severity="warning",
                )
            )
        return findings
