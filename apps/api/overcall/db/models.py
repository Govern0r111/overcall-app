from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, SQLModel


class SupabaseAuthUser(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}

    id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), primary_key=True))


class UserSettings(SQLModel, table=True):
    __tablename__ = "user_settings"

    user_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("auth.users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    currency: str = Field(
        default="INR", sa_column=Column(Text, nullable=False, server_default="INR")
    )
    usd_inr_rate: Decimal = Field(
        default=Decimal("83.5"),
        sa_column=Column(Numeric(10, 4), nullable=False, server_default="83.5"),
    )
    rules_enabled: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    tier3_enabled: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false"))
    )
    thresholds: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    upstream_mode: str = Field(
        default="mock", sa_column=Column(Text, nullable=False, server_default="mock")
    )
    retention_days: int = Field(
        default=14, sa_column=Column(Integer, nullable=False, server_default="14")
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )


class IngestKey(SQLModel, table=True):
    __tablename__ = "ingest_keys"

    id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
        ),
    )
    user_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
        )
    )
    name: str = Field(sa_column=Column(Text, nullable=False))
    prefix: str = Field(sa_column=Column(Text, nullable=False))
    key_hash: str = Field(sa_column=Column(Text, nullable=False, unique=True))
    pepper_version: int = Field(
        default=1, sa_column=Column(SmallInteger, nullable=False, server_default="1")
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )
    last_used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    revoked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class RequestLog(SQLModel, table=True):
    __tablename__ = "request_logs"

    id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
        ),
    )
    user_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
        )
    )
    ingest_key_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("ingest_keys.id", ondelete="SET NULL"), nullable=True
        ),
    )
    source: str = Field(sa_column=Column(Text, nullable=False))
    origin: str = Field(
        default="upstream", sa_column=Column(Text, nullable=False, server_default="upstream")
    )
    occurred_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    provider: str = Field(sa_column=Column(Text, nullable=False))
    method: str = Field(sa_column=Column(Text, nullable=False))
    endpoint: str = Field(sa_column=Column(Text, nullable=False))
    status: int = Field(sa_column=Column(Integer, nullable=False))
    latency_ms: float = Field(sa_column=Column(Float(precision=24), nullable=False))
    ttfb_ms: float | None = Field(
        default=None, sa_column=Column(Float(precision=24), nullable=True)
    )
    req_size: int = Field(sa_column=Column(Integer, nullable=False))
    resp_size: int = Field(sa_column=Column(Integer, nullable=False))
    req_hash: str = Field(sa_column=Column(Text, nullable=False))
    model: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    prompt_tokens: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    completion_tokens: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    cached_prompt_tokens: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    tokens_estimated: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false"))
    )
    stream: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false"))
    )
    context_hash: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    context_tokens: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    uses_tools: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false"))
    )
    list_limit: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    items_returned: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    has_idempotency_key: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false"))
    )
    caller: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    cost_usd: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(14, 8), nullable=False, server_default="0"),
    )
    cost_basis: str = Field(sa_column=Column(Text, nullable=False))
    pricing_version: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    error_code: str | None = Field(default=None, sa_column=Column(Text, nullable=True))


class DetectionRun(SQLModel, table=True):
    __tablename__ = "detection_runs"

    id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
        ),
    )
    user_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
        )
    )
    status: str = Field(sa_column=Column(Text, nullable=False))
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    is_demo_data: bool = Field(sa_column=Column(Boolean, nullable=False))
    window_start: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    window_end: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    window_days: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(8, 3), nullable=True)
    )
    projection_low_confidence: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False, server_default=text("false"))
    )
    request_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    flagged_request_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    total_spend_usd: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(14, 6), nullable=False, server_default="0")
    )
    spend_savings_window_usd: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(14, 6), nullable=False, server_default="0")
    )
    spend_savings_monthly_usd: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(14, 6), nullable=False, server_default="0")
    )
    experimental_monthly_usd: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(14, 6), nullable=False, server_default="0")
    )
    reliability_count: int = Field(
        default=0, sa_column=Column(Integer, nullable=False, server_default="0")
    )
    reliability_overhead_monthly_usd: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(14, 6), nullable=False, server_default="0")
    )
    issue_counts: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    trend: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    settings_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    pricing_versions: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    rule_errors: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )
    duration_ms: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))


class Issue(SQLModel, table=True):
    __tablename__ = "issues"

    id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
        ),
    )
    user_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False
        )
    )
    run_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("detection_runs.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    rule_id: str = Field(sa_column=Column(Text, nullable=False))
    tier: int = Field(sa_column=Column(Integer, nullable=False))
    experimental: bool = Field(sa_column=Column(Boolean, nullable=False))
    provider: str = Field(sa_column=Column(Text, nullable=False))
    endpoint: str = Field(sa_column=Column(Text, nullable=False))
    severity: str = Field(sa_column=Column(Text, nullable=False))
    impact_kind: str = Field(sa_column=Column(Text, nullable=False))
    title: str = Field(sa_column=Column(Text, nullable=False))
    summary: str = Field(sa_column=Column(Text, nullable=False))
    explanation: str = Field(sa_column=Column(Text, nullable=False))
    suggested_fix: str = Field(sa_column=Column(Text, nullable=False))
    affected_count: int = Field(sa_column=Column(Integer, nullable=False))
    window_savings_usd: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(14, 6), nullable=False, server_default="0")
    )
    projected_monthly_usd: Decimal = Field(
        default=Decimal("0"), sa_column=Column(Numeric(14, 6), nullable=False, server_default="0")
    )
    confidence: float | None = Field(
        default=None, sa_column=Column(Float(precision=24), nullable=True)
    )
    is_demo_data: bool = Field(sa_column=Column(Boolean, nullable=False))
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )


class IssueRequest(SQLModel, table=True):
    __tablename__ = "issue_requests"

    issue_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("issues.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    request_id: UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("request_logs.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
    )
    user_id: UUID = Field(sa_column=Column(PGUUID(as_uuid=True), nullable=False))
    waste_usd: Decimal = Field(
        default=Decimal("0"),
        sa_column=Column(Numeric(14, 8), nullable=False, server_default="0"),
    )
