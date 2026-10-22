from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

Severity = Literal["critical", "warning", "info"]
ImpactKind = Literal["spend", "reliability"]
CostBasis = Literal["billed", "estimated", "modelled"]
ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class LogRow:
    id: UUID
    occurred_at: datetime
    provider: str
    method: str
    endpoint: str
    status: int
    latency_ms: float
    req_size: int
    resp_size: int
    req_hash: str
    cost_usd: Decimal
    cost_basis: CostBasis
    pricing_version: str | None
    source: Literal["proxy", "demo"]
    origin: Literal["upstream", "overcall"]
    caller: str | None = None
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_prompt_tokens: int = 0
    tokens_estimated: bool = False
    stream: bool = False
    context_hash: str | None = None
    context_tokens: int | None = None
    uses_tools: bool = False
    list_limit: int | None = None
    items_returned: int | None = None
    has_idempotency_key: bool = False

    @classmethod
    def from_record(cls, record: dict[str, object]) -> LogRow:
        timestamp = record.get("occurred_at", record.get("timestamp"))
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
            raise ValueError("LogRow occurred_at must be a timezone-aware datetime")

        cost = record.get("cost_usd", ZERO)
        return cls(
            id=UUID(str(record["id"])),
            occurred_at=timestamp,
            provider=str(record["provider"]),
            method=str(record["method"]),
            endpoint=str(record["endpoint"]),
            status=int(record["status"]),
            latency_ms=float(record.get("latency_ms", 0)),
            req_size=int(record.get("req_size", 0)),
            resp_size=int(record.get("resp_size", 0)),
            req_hash=str(record["req_hash"]),
            cost_usd=cost if isinstance(cost, Decimal) else Decimal(str(cost)),
            cost_basis=str(record.get("cost_basis", "modelled")),  # type: ignore[arg-type]
            pricing_version=(
                str(record["pricing_version"])
                if record.get("pricing_version") is not None
                else None
            ),
            source=str(record.get("source", "demo")),  # type: ignore[arg-type]
            origin=str(record.get("origin", "upstream")),  # type: ignore[arg-type]
            caller=record.get("caller") if isinstance(record.get("caller"), str) else None,
            model=record.get("model") if isinstance(record.get("model"), str) else None,
            prompt_tokens=int(record.get("prompt_tokens", 0)),
            completion_tokens=int(record.get("completion_tokens", 0)),
            cached_prompt_tokens=int(record.get("cached_prompt_tokens", 0)),
            tokens_estimated=bool(record.get("tokens_estimated", False)),
            stream=bool(record.get("stream", False)),
            context_hash=(
                record.get("context_hash") if isinstance(record.get("context_hash"), str) else None
            ),
            context_tokens=(
                int(record["context_tokens"]) if record.get("context_tokens") is not None else None
            ),
            uses_tools=bool(record.get("uses_tools", False)),
            list_limit=int(record["list_limit"]) if record.get("list_limit") is not None else None,
            items_returned=(
                int(record["items_returned"]) if record.get("items_returned") is not None else None
            ),
            has_idempotency_key=bool(record.get("has_idempotency_key", False)),
        )

    @classmethod
    def from_model(cls, row: object) -> LogRow:
        fields = (
            "id",
            "occurred_at",
            "provider",
            "method",
            "endpoint",
            "status",
            "latency_ms",
            "req_size",
            "resp_size",
            "req_hash",
            "cost_usd",
            "cost_basis",
            "pricing_version",
            "source",
            "origin",
            "caller",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "cached_prompt_tokens",
            "tokens_estimated",
            "stream",
            "context_hash",
            "context_tokens",
            "uses_tools",
            "list_limit",
            "items_returned",
            "has_idempotency_key",
        )
        return cls.from_record({name: getattr(row, name) for name in fields})


@dataclass(slots=True)
class Finding:
    rule_id: str
    severity: Severity
    provider: str
    endpoint: str
    title: str
    summary: str
    explanation: str
    suggested_fix: str
    affected: list[LogRow]
    waste_by_request: dict[UUID, Decimal]
    tier: Literal[1, 2, 3] = 1
    impact_kind: ImpactKind = "spend"
    confidence: float | None = None
    experimental: bool = False
    critical_at: Decimal = Decimal("20")
    warning_at: Decimal = Decimal("2")
    minimum_severity: Severity | None = None
    _money_risk: bool = field(default=False, repr=False)

    @property
    def window_savings_usd(self) -> Decimal:
        return sum(self.waste_by_request.values(), ZERO)


@dataclass(frozen=True, slots=True)
class RuleContext:
    thresholds: object
    window_days: float
    now: datetime

    def monthly(self, amount: Decimal) -> Decimal:
        return amount * Decimal("30") / Decimal(str(max(self.window_days, 1.0)))


class Rule(Protocol):
    id: str
    name: str
    tier: Literal[1, 2, 3]
    description: str
    default_enabled: bool
    threshold_keys: tuple[str, ...]

    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]: ...


def ordered_logs(logs: Sequence[LogRow]) -> list[LogRow]:
    return sorted(
        (row for row in logs if row.origin != "overcall" and row.provider != "aws"),
        key=lambda row: (row.occurred_at, row.id),
    )


def is_success(status: int) -> bool:
    return 200 <= status < 300
