from __future__ import annotations

from sqlalchemy import case, true
from sqlalchemy.sql.elements import ColumnElement

from ..db.models import Issue as IssueModel
from ..detection.registry import RULES_BY_ID
from .schemas import Issue, usd

SEVERITY_ORDER = case(
    (IssueModel.severity == "critical", 0),
    (IssueModel.severity == "warning", 1),
    else_=2,
)


def impact_order() -> tuple[ColumnElement, ...]:
    """Severity first, spend before reliability, then largest projected saving, then id."""
    return (
        SEVERITY_ORDER,
        case((IssueModel.impact_kind == "spend", 0), else_=1),
        IssueModel.projected_monthly_usd.desc(),
        IssueModel.id,
    )


def experimental_visible(tier3_enabled: bool, include_experimental: bool) -> ColumnElement:
    """Tier 3 issues need the user's setting AND an explicit request for them."""
    if tier3_enabled and include_experimental:
        return true()
    return IssueModel.experimental.is_(False)


def rule_name(rule_id: str) -> str:
    rule = RULES_BY_ID.get(rule_id)
    return rule.name if rule else rule_id


def issue_to_schema(row: IssueModel) -> Issue:
    return Issue(
        id=row.id,
        rule_id=row.rule_id,
        rule_name=rule_name(row.rule_id),
        tier=row.tier,
        experimental=row.experimental,
        provider=row.provider,
        endpoint=row.endpoint,
        severity=row.severity,
        impact_kind=row.impact_kind,
        title=row.title,
        summary=row.summary,
        explanation=row.explanation,
        suggested_fix=row.suggested_fix,
        affected_count=row.affected_count,
        window_savings_usd=usd(row.window_savings_usd),
        projected_monthly_usd=usd(row.projected_monthly_usd),
        confidence=row.confidence,
        is_demo_data=row.is_demo_data,
        detected_at=row.detected_at,
    )
