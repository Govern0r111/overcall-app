from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from .base import Finding, LogRow, Severity

ZERO = Decimal("0")


def monthly_projection(window_savings: Decimal, window_days: float) -> Decimal:
    return window_savings * Decimal("30") / Decimal(str(max(window_days, 1.0)))


def clamp_waste(amount: Decimal, cost: Decimal) -> Decimal:
    return min(max(amount, ZERO), max(cost, ZERO))


def severity_for(
    monthly_usd: Decimal,
    *,
    critical_at: Decimal = Decimal("20"),
    warning_at: Decimal = Decimal("2"),
) -> Severity:
    if monthly_usd >= critical_at:
        return "critical"
    if monthly_usd >= warning_at:
        return "warning"
    return "info"


def split_by_impact(finding: Finding, window_days: float) -> list[Finding]:
    """Separate billed/estimated spend from modelled and Stripe reliability impact."""
    rows = {row.id: row for row in finding.affected}
    partitions: dict[str, tuple[list[LogRow], dict]] = {
        "spend": ([], {}),
        "reliability": ([], {}),
    }
    for request_id, waste in finding.waste_by_request.items():
        row = rows.get(request_id)
        if row is None:
            continue
        impact = (
            "reliability" if row.provider == "stripe" or row.cost_basis == "modelled" else "spend"
        )
        affected, waste_map = partitions[impact]
        affected.append(row)
        waste_map[request_id] = clamp_waste(waste, row.cost_usd)

    result = []
    for impact_kind, (affected, waste_map) in partitions.items():
        if not affected:
            continue
        issue = replace(
            finding,
            affected=affected,
            waste_by_request=waste_map,
            impact_kind=impact_kind,
            severity=(
                "critical"
                if finding._money_risk and impact_kind == "reliability"
                else severity_for(
                    monthly_projection(sum(waste_map.values(), ZERO), window_days),
                    critical_at=finding.critical_at,
                    warning_at=finding.warning_at,
                )
            ),
            _money_risk=finding._money_risk and impact_kind == "reliability",
        )
        if issue.minimum_severity is not None and ["info", "warning", "critical"].index(
            issue.severity
        ) < ["info", "warning", "critical"].index(issue.minimum_severity):
            issue.severity = issue.minimum_severity
        result.append(issue)
    return result
