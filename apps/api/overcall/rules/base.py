from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List

from ..models import RequestLog
from ..pricing_config import is_ok  # noqa: F401  (re-exported for rules)

PROVIDER_LABEL = {"openai": "OpenAI", "stripe": "Stripe", "aws": "AWS"}


@dataclass
class Finding:
    issue_type: str
    severity: str
    provider: str
    endpoint: str
    title: str
    summary: str
    explanation: str
    suggested_fix: str
    affected: List[RequestLog]
    waste_by_request: Dict[str, float]
    confidence: float = 1.0

    @property
    def estimated_savings(self) -> float:
        return sum(self.waste_by_request.values())


@dataclass
class RuleContext:
    w: object
    window_days: float

    def monthly(self, usd: float) -> float:
        return usd * 30 / self.window_days


class Rule(ABC):
    id: str
    name: str
    tier: int
    description: str

    @abstractmethod
    def detect(self, logs: List[RequestLog], ctx: RuleContext) -> List[Finding]:
        ...


def gap_s(a: RequestLog, b: RequestLog) -> float:
    return (b.timestamp - a.timestamp).total_seconds()


def group_by(items, key) -> dict:
    out: dict = {}
    for it in items:
        out.setdefault(key(it), []).append(it)
    return out


def by_endpoint(flagged: List[RequestLog]) -> dict:
    return group_by(flagged, lambda l: (l.provider, l.endpoint))


def severity_for(monthly_usd: float, critical_at: float = 20.0, warning_at: float = 2.0) -> str:
    if monthly_usd >= critical_at:
        return "critical"
    return "warning" if monthly_usd >= warning_at else "info"
