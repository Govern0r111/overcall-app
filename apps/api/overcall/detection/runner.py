from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import DetectionRun, Issue, IssueRequest, UserSettings
from ..db.repos import IssuesRepository, LogsRepository, RunsRepository
from .base import Finding, LogRow, Rule, RuleContext
from .registry import RULES
from .savings import monthly_projection, split_by_impact
from .thresholds import Thresholds

MAX_LOGS = 200_000
LOOKBACK = timedelta(days=30)
ZERO = Decimal("0")
SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}
_RUN_OPTIONS = text("SELECT pg_advisory_xact_lock(hashtextextended(:user_id, 0))")


def _window_days(logs: list[LogRow]) -> float:
    if not logs:
        return 0.0
    return max(0.0, (logs[-1].occurred_at - logs[0].occurred_at).total_seconds() / 86_400)


def _enabled_rules(settings: UserSettings | None) -> dict[str, bool]:
    configured = settings.rules_enabled if settings else {}
    return {rule.id: configured.get(rule.id, rule.default_enabled) for rule in RULES}


def _thresholds(settings: UserSettings | None) -> Thresholds:
    overrides = settings.thresholds if settings else {}
    return Thresholds.model_validate(overrides)


def _settings_snapshot(
    settings: UserSettings | None,
    enabled: dict[str, bool],
    thresholds: Thresholds,
) -> dict[str, Any]:
    return {
        "rules_enabled": enabled,
        "tier3_enabled": settings.tier3_enabled if settings else False,
        "thresholds": thresholds.model_dump(mode="json"),
    }


def _waste_max(findings: list[Finding]) -> dict[UUID, Decimal]:
    result: dict[UUID, Decimal] = {}
    for finding in findings:
        for request_id, amount in finding.waste_by_request.items():
            result[request_id] = max(result.get(request_id, ZERO), amount)
    return result


def _trend(logs: list[LogRow], spend_waste: dict[UUID, Decimal]) -> list[dict[str, Any]]:
    days: dict[str, dict[str, Decimal | str]] = {}
    for row in logs:
        key = row.occurred_at.date().isoformat()
        day = days.setdefault(key, {"date": key, "spend_usd": ZERO, "waste_usd": ZERO})
        if row.cost_basis in {"billed", "estimated"}:
            day["spend_usd"] += row.cost_usd
            day["waste_usd"] += spend_waste.get(row.id, ZERO)
    return [
        {
            "date": value["date"],
            "spend_usd": float(round(value["spend_usd"], 6)),
            "waste_usd": float(round(value["waste_usd"], 6)),
        }
        for _, value in sorted(days.items())
    ]


def build_summary(
    logs: list[LogRow],
    findings: list[Finding],
    window_days: float,
    rule_errors: list[dict[str, str]],
    settings_snapshot: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int,
    is_demo_data: bool,
) -> dict[str, Any]:
    trusted_spend = [
        finding
        for finding in findings
        if finding.impact_kind == "spend" and not finding.experimental and finding.tier <= 2
    ]
    experimental = [
        finding for finding in findings if finding.impact_kind == "spend" and finding.experimental
    ]
    reliability = [finding for finding in findings if finding.impact_kind == "reliability"]
    spend_waste = _waste_max(trusted_spend)
    experimental_waste = _waste_max(experimental)
    reliability_waste = _waste_max(reliability)
    spend_total = sum(
        (row.cost_usd for row in logs if row.cost_basis in {"billed", "estimated"}),
        ZERO,
    )
    all_flagged = {row.id for finding in findings for row in finding.affected}
    severity_counts = {
        severity: sum(finding.severity == severity for finding in findings)
        for severity in SEVERITY_RANK
    }
    pricing_versions: dict[str, list[str]] = defaultdict(list)
    for row in logs:
        if row.pricing_version and row.pricing_version not in pricing_versions[row.provider]:
            pricing_versions[row.provider].append(row.pricing_version)

    return {
        "status": "succeeded",
        "started_at": started_at,
        "finished_at": finished_at,
        "is_demo_data": is_demo_data,
        "window_start": logs[0].occurred_at if logs else None,
        "window_end": logs[-1].occurred_at if logs else None,
        "window_days": Decimal(str(round(window_days, 3))) if logs else None,
        "projection_low_confidence": bool(logs) and window_days < 1,
        "request_count": len(logs),
        "flagged_request_count": len(all_flagged),
        "total_spend_usd": spend_total.quantize(Decimal("0.000001")),
        "spend_savings_window_usd": sum(spend_waste.values(), ZERO).quantize(Decimal("0.000001")),
        "spend_savings_monthly_usd": monthly_projection(
            sum(spend_waste.values(), ZERO), window_days
        ).quantize(Decimal("0.000001")),
        "experimental_monthly_usd": monthly_projection(
            sum(experimental_waste.values(), ZERO), window_days
        ).quantize(Decimal("0.000001")),
        "reliability_count": len(reliability),
        "reliability_overhead_monthly_usd": monthly_projection(
            sum(reliability_waste.values(), ZERO), window_days
        ).quantize(Decimal("0.000001")),
        "issue_counts": severity_counts,
        "trend": _trend(logs, spend_waste),
        "settings_snapshot": settings_snapshot,
        "pricing_versions": dict(pricing_versions),
        "rule_errors": rule_errors,
        "duration_ms": duration_ms,
    }


class DetectionRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        rules: tuple[Rule, ...] = RULES,
    ) -> None:
        self.session_factory = session_factory
        self.rules = rules

    async def run(self, user_id: UUID, run_id: UUID | None = None) -> DetectionRun:
        started_clock = time.perf_counter()
        started_at = datetime.now(UTC)
        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(
                    _RUN_OPTIONS,
                    {"user_id": str(user_id)},
                )
                settings = await session.get(UserSettings, user_id)
                thresholds = _thresholds(settings)
                enabled = _enabled_rules(settings)
                logs_models, source = await LogsRepository(session, user_id).load_detection_window(
                    started_at - LOOKBACK, MAX_LOGS
                )
                logs = [LogRow.from_model(row) for row in logs_models]
                days = _window_days(logs)
                context = RuleContext(
                    thresholds=thresholds,
                    window_days=days if days > 0 else 1.0,
                    now=started_at,
                )

                findings: list[Finding] = []
                rule_errors: list[dict[str, str]] = []
                for rule in self.rules:
                    if not enabled.get(rule.id, rule.default_enabled):
                        continue
                    if rule.tier == 3 and not (settings and settings.tier3_enabled):
                        continue
                    try:
                        for finding in rule.detect(logs, context):
                            findings.extend(split_by_impact(finding, context.window_days))
                    except Exception as exc:
                        rule_errors.append({"rule_id": rule.id, "error_type": type(exc).__name__})

                findings.sort(
                    key=lambda finding: (
                        SEVERITY_RANK[finding.severity],
                        finding.impact_kind != "spend",
                        finding.rule_id,
                        finding.provider,
                        finding.endpoint,
                    )
                )
                finished_at = datetime.now(UTC)
                duration_ms = round((time.perf_counter() - started_clock) * 1000)
                snapshot = _settings_snapshot(settings, enabled, thresholds)
                summary = build_summary(
                    logs,
                    findings,
                    days,
                    rule_errors,
                    snapshot,
                    started_at,
                    finished_at,
                    duration_ms,
                    source == "demo",
                )
                run = DetectionRun(
                    id=run_id or uuid4(),
                    user_id=user_id,
                    **summary,
                )

                issues = []
                issue_requests = []
                for finding in findings:
                    issue_id = uuid4()
                    issues.append(
                        Issue(
                            id=issue_id,
                            user_id=user_id,
                            run_id=run.id,
                            rule_id=finding.rule_id,
                            tier=finding.tier,
                            experimental=finding.experimental,
                            provider=finding.provider,
                            endpoint=finding.endpoint,
                            severity=finding.severity,
                            impact_kind=finding.impact_kind,
                            title=finding.title,
                            summary=finding.summary,
                            explanation=finding.explanation,
                            suggested_fix=finding.suggested_fix,
                            affected_count=len(finding.affected),
                            window_savings_usd=finding.window_savings_usd.quantize(
                                Decimal("0.000001")
                            ),
                            projected_monthly_usd=monthly_projection(
                                finding.window_savings_usd, context.window_days
                            ).quantize(Decimal("0.000001")),
                            confidence=finding.confidence,
                            is_demo_data=source == "demo",
                            detected_at=finished_at,
                        )
                    )
                    for request_id, amount in list(finding.waste_by_request.items())[:200]:
                        issue_requests.append(
                            IssueRequest(
                                issue_id=issue_id,
                                request_id=request_id,
                                user_id=user_id,
                                waste_usd=amount.quantize(Decimal("0.00000001")),
                            )
                        )

                await IssuesRepository(session, user_id).delete_for_user()
                RunsRepository(session).add(run)
                await session.flush()
                IssuesRepository(session, user_id).add_all(issues, issue_requests)
                await session.flush()
                return run
