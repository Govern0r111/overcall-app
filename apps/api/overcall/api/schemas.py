from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")

Severity = Literal["critical", "warning", "info"]
ImpactKind = Literal["spend", "reliability"]
ProviderId = Literal["openai", "stripe", "aws"]


def usd(value: Decimal | float | None) -> float:
    """Money leaves the API as a JSON number in USD, rounded to 6 decimals."""
    if value is None:
        return 0.0
    return round(float(value), 6)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(ApiModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class Me(ApiModel):
    id: UUID
    email: str | None
    created_at: datetime | None
    proxy_status: Literal["no_key", "waiting_for_traffic", "receiving_traffic", "demo_only"]
    last_request_at: datetime | None
    issue_count: int
    is_demo_data: bool
    has_data: bool
    real_upstream_available: bool


class SampleRequest(ApiModel):
    request_id: UUID
    occurred_at: datetime
    req_hash: str
    req_size: int
    resp_size: int
    status: int
    cost_usd: float


class Issue(ApiModel):
    id: UUID
    rule_id: str
    rule_name: str
    tier: Literal[1, 2, 3]
    experimental: bool
    provider: ProviderId
    endpoint: str
    severity: Severity
    impact_kind: ImpactKind
    title: str
    summary: str
    explanation: str
    suggested_fix: str
    affected_count: int
    window_savings_usd: float
    projected_monthly_usd: float
    confidence: float | None
    is_demo_data: bool
    detected_at: datetime


class IssueDetail(Issue):
    sample_requests: list[SampleRequest]


class FlaggedBy(ApiModel):
    issue_id: UUID
    rule_id: str
    title: str
    severity: Severity


class LogEntry(ApiModel):
    id: UUID
    occurred_at: datetime
    provider: ProviderId
    method: str
    endpoint: str
    status: int
    latency_ms: float
    ttfb_ms: float | None
    req_size: int
    resp_size: int
    req_hash: str
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    tokens_estimated: bool
    stream: bool
    cost_usd: float
    cost_basis: Literal["billed", "estimated", "modelled"]
    pricing_version: str | None
    caller: str | None
    has_idempotency_key: bool
    error_code: str | None
    origin: Literal["upstream", "overcall"]
    is_demo: bool
    flagged_by: list[FlaggedBy]


class FacetValue(ApiModel):
    value: str
    count: int


class LogFacets(ApiModel):
    providers: list[FacetValue]
    endpoints: list[FacetValue]
    callers: list[FacetValue]
    models: list[FacetValue]


class OverviewWindow(ApiModel):
    start: datetime | None
    end: datetime | None
    days: float
    low_confidence_projection: bool


class SpendSavings(ApiModel):
    window_usd: float
    projected_monthly_usd: float
    percent_of_spend: float


class ExperimentalSavings(ApiModel):
    projected_monthly_usd: float


class ReliabilityFindings(ApiModel):
    count: int
    modelled_overhead_monthly_usd: float


class SeverityBreakdown(ApiModel):
    critical: int = 0
    warning: int = 0
    info: int = 0


class ProviderBreakdown(ApiModel):
    provider: ProviderId
    spend_usd: float
    issue_count: int


class TrendPoint(ApiModel):
    date: str
    spend_usd: float
    waste_usd: float


class Overview(ApiModel):
    has_data: bool
    is_demo_data: bool
    generated_at: datetime | None
    run_id: UUID | None
    window: OverviewWindow
    request_count: int
    flagged_request_count: int
    total_spend_usd: float
    spend_savings: SpendSavings
    experimental_spend_savings: ExperimentalSavings
    reliability_findings: ReliabilityFindings
    severity_breakdown: SeverityBreakdown
    by_provider: list[ProviderBreakdown]
    trend: list[TrendPoint]
    top_issues: list[Issue]


class Snippet(ApiModel):
    id: str
    label: str
    code: str


class ProviderTraffic(ApiModel):
    proxy: int
    demo: int
    last_request_at: datetime | None


class PricingRow(ApiModel):
    label: str
    usd_per_1m: float | None = None
    usd_per_request: float | None = None


class ProviderPricing(ApiModel):
    version: str
    effective_from: datetime
    source_url: str
    rows: list[PricingRow]


class Provider(ApiModel):
    id: ProviderId
    name: str
    status: Literal["waiting", "receiving_traffic", "demo_only", "coming_soon"]
    proxy_base_url: str | None
    snippets: list[Snippet]
    traffic: ProviderTraffic
    upstream_mode: Literal["mock", "real", "test"] | None
    pricing: ProviderPricing | None
    notes: str | None


class SettingsOut(ApiModel):
    currency: Literal["INR", "USD"]
    usd_inr_rate: float
    rules_enabled: dict[str, bool]
    tier3_enabled: bool
    thresholds: dict[str, float]
    upstream_mode: Literal["mock", "real"]
    confirm_real_upstream: bool = False
    retention_days: int
    updated_at: datetime


class SettingsIn(ApiModel):
    currency: Literal["INR", "USD"]
    usd_inr_rate: float = Field(gt=0, le=10_000)
    rules_enabled: dict[str, bool]
    tier3_enabled: bool
    thresholds: dict[str, Any]
    upstream_mode: Literal["mock", "real"]
    confirm_real_upstream: bool = False
    retention_days: int = Field(ge=1, le=90)
    updated_at: datetime | None = None


class RuleInfo(ApiModel):
    id: str
    name: str
    tier: Literal[1, 2, 3]
    description: str
    default_enabled: bool
    threshold_keys: list[str]


class RunSummary(ApiModel):
    run_id: UUID | None
    status: Literal["running", "succeeded", "failed", "none"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    request_count: int = 0
    issue_counts: dict[str, int] = Field(default_factory=dict)
    rule_errors: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int | None = None


class DemoLoadIn(ApiModel):
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    days: int = Field(default=7, ge=1, le=30)


class DemoLoadOut(ApiModel):
    inserted: int


class AccuracyRule(ApiModel):
    rule_id: str
    tier: int
    positives: int
    flagged: int
    true_positives: int
    precision: float | None
    recall: float | None
    false_positives_on_hard_negatives: int | None = None
    wilson_low: float | None = None
    wilson_high: float | None = None


class AccuracyDataset(ApiModel):
    id: Literal["synthetic", "real"]
    label: str
    note: str
    generated_at: datetime | None
    requests: int
    rules: list[AccuracyRule]


class Accuracy(ApiModel):
    datasets: list[AccuracyDataset]


class IngestKeyCreate(ApiModel):
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name must not be blank.")
        if len(normalized) > 60:
            raise ValueError("Name must be at most 60 characters.")
        return normalized


class IngestKeyOut(ApiModel):
    id: UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class CreatedIngestKey(IngestKeyOut):
    key: str


class IngestKeyPage(Page[IngestKeyOut]):
    pass
