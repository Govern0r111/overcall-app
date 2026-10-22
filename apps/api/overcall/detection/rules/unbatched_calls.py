from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal

from ...pricing import DEFAULT_PRICING_BOOK
from ..base import Finding, LogRow, RuleContext, is_success, ordered_logs
from ..savings import clamp_waste
from .common import gap_seconds, group_by, monthly_rule_severity


def _template_pattern(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}/]+\})", template)
    regex = "".join(
        "[^/]+" if part.startswith("{") and part.endswith("}") else re.escape(part)
        for part in parts
    )
    return re.compile(f"^{regex}$")


def batch_equivalent_for(row: LogRow):
    """Return (template, equivalent) for a documented batch alternative, if one exists."""
    pricing = DEFAULT_PRICING_BOOK.for_time(row.provider, row.occurred_at)
    for key, equivalent in pricing.batch_equivalents.items():
        method, _, template = key.partition(" ")
        if method == row.method and _template_pattern(template).match(row.endpoint):
            return template, equivalent
    return None


def bursts(group: list[LogRow], window_s: float, minimum: int) -> list[list[LogRow]]:
    result: list[list[LogRow]] = []
    current = [group[0]]
    for previous, row in zip(group, group[1:], strict=False):
        if gap_seconds(previous, row) <= window_s:
            current.append(row)
        else:
            if len(current) >= minimum:
                result.append(current)
            current = [row]
    if len(current) >= minimum:
        result.append(current)
    return result


class UnbatchedCalls:
    id = "unbatched_calls"
    name = "Unbatched calls"
    tier = 2
    description = "Bursts of separate calls to an endpoint that has a documented batch alternative."
    default_enabled = True
    threshold_keys = ("unbatched_min_calls", "unbatched_window_s")

    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]:
        window = float(ctx.thresholds.unbatched_window_s)
        minimum = int(ctx.thresholds.unbatched_min_calls)

        candidates = []
        for row in ordered_logs(logs):
            if not is_success(row.status):
                continue
            match = batch_equivalent_for(row)
            if match is not None:
                candidates.append((row, match[0], match[1]))
        equivalents = {(row.id): equivalent for row, _, equivalent in candidates}
        groups = group_by(
            candidates,
            lambda item: (item[0].provider, item[0].method, item[1], item[0].caller or "unknown"),
        )

        by_template: dict[tuple[str, str, str], list[LogRow]] = {}
        for key, items in groups.items():
            provider, method, template, _caller = key
            rows = [item[0] for item in items]
            for burst in bursts(rows, window, minimum):
                by_template.setdefault((provider, method, template), []).extend(burst[1:])

        findings = []
        for (provider, _method, template), repeats in sorted(by_template.items()):
            repeats.sort(key=lambda row: (row.occurred_at, row.id))
            equivalent = equivalents[repeats[0].id]
            waste = {
                row.id: clamp_waste(row.cost_usd * equivalent.discount, row.cost_usd)
                for row in repeats
            }
            findings.append(
                Finding(
                    rule_id=self.id,
                    tier=2,
                    severity=monthly_rule_severity(
                        sum(waste.values(), Decimal("0")), ctx.window_days, self.id
                    ),
                    provider=provider,
                    endpoint=template,
                    title=f"Calls to {template} could be batched",
                    summary=(
                        f"{len(repeats)} follow-up calls to {template} arrived in bursts of "
                        f"{minimum} or more calls, each within {window:g}s of the last."
                    ),
                    explanation=(f"{equivalent.method} Basis for the estimate: {equivalent.basis}"),
                    suggested_fix=equivalent.fix,
                    affected=repeats,
                    waste_by_request=waste,
                )
            )
        return findings
