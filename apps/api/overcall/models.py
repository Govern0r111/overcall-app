from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(default_factory=lambda: str(uuid4()), alias="_id")

    @classmethod
    def from_record(cls, doc: dict | None) -> BaseDocument | None:
        if not doc:
            return None
        if "_id" in doc and "id" not in doc:
            doc = {**doc, "id": str(doc["_id"])}
        return cls.model_validate(doc)

    from_mongo = from_record

    def to_record(self) -> dict:
        return self.model_dump(by_alias=True)

    to_mongo = to_record


class RequestLog(BaseDocument):
    timestamp: datetime
    provider: str
    endpoint: str
    method: str
    req_size: int
    req_hash: str
    status: int
    resp_size: int
    latency_ms: float
    cost_usd: float
    cost_basis: str = "modelled"
    pricing_version: str | None = None
    source: str
    origin: str = "upstream"
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
    error_code: str | None = None


class Issue(BaseDocument):
    rule_id: str
    rule_name: str
    issue_type: str
    tier: int
    experimental: bool
    provider: str
    endpoint: str
    severity: str
    title: str
    summary: str
    explanation: str
    suggested_fix: str
    affected_requests: list[str]
    affected_count: int
    estimated_savings_usd: float
    projected_monthly_usd: float
    confidence: float
    sample_requests: list[dict[str, Any]]
    detected_at: datetime
