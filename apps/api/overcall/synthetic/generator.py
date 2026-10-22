from __future__ import annotations

import hashlib
import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..pricing import Usage
from ..pricing.cost import estimate_cost
from .scenarios import inject_scenarios
from .truth import GroundTruth, GroundTruthLabel

GENERATOR_VERSION = "1.1.0"
_NAMESPACE = uuid.NAMESPACE_URL
_DAYS_SECONDS = 86_400
_SMALL_BASELINE_PER_WEEK = 160
_STANDARD_BASELINE_PER_WEEK = 6_800
_MAX_STANDARD_BASELINE = 9_000
_DIURNAL_WEIGHTS = (1, 1, 1, 1, 1, 2, 4, 7, 9, 9, 9, 9, 9, 9, 9, 9, 9, 9, 8, 6, 4, 3, 2, 1)


class LogRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    occurred_at: datetime
    provider: str
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
    cost_basis: str
    pricing_version: str
    caller: str | None
    has_idempotency_key: bool = Field(default=False, exclude=True)
    error_code: str | None
    origin: str
    is_demo: bool
    flagged_by: list[dict[str, Any]] = Field(default_factory=list)
    source: str = Field(default="demo", exclude=True)
    context_hash: str | None = Field(default=None, exclude=True)
    context_tokens: int | None = Field(default=None, exclude=True)
    uses_tools: bool = Field(default=False, exclude=True)
    list_limit: int | None = Field(default=None, exclude=True)
    items_returned: int | None = Field(default=None, exclude=True)
    cached_prompt_tokens: int = Field(default=0, exclude=True)

    @property
    def timestamp(self) -> datetime:
        return self.occurred_at

    def to_record(self) -> dict[str, Any]:
        record = self.model_dump(mode="python")
        record.update(
            {
                "timestamp": self.occurred_at,
                "source": self.source,
                "context_hash": self.context_hash,
                "context_tokens": self.context_tokens,
                "uses_tools": self.uses_tools,
                "list_limit": self.list_limit,
                "items_returned": self.items_returned,
                "has_idempotency_key": self.has_idempotency_key,
                "cached_prompt_tokens": self.cached_prompt_tokens,
            }
        )
        return record


class SyntheticGenerator:
    def __init__(self, seed: int, days: int, size: str, start: datetime):
        self.seed = seed
        self.days = days
        self.size = size
        self.start = start.astimezone(UTC).replace(microsecond=0)
        self.rng = random.Random(seed)
        self.logs: list[LogRow] = []
        self.labels: list[GroundTruthLabel] = []

    def hash_for(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    def when(self, day: int | None = None) -> datetime:
        day = self.rng.randrange(self.days) if day is None else day % self.days
        hour = self.rng.choices(range(24), weights=_DIURNAL_WEIGHTS)[0]
        return self.start + timedelta(
            days=day,
            hours=hour,
            seconds=self.rng.randrange(3_600),
        )

    def add(
        self,
        timestamp: datetime,
        provider: str,
        method: str,
        endpoint: str,
        *,
        status: int = 200,
        model: str | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        req_hash: str | None = None,
        h: str | None = None,
        ctx: str | None = None,
        req_size: int | None = None,
        resp_size: int | None = None,
        context_hash: str | None = None,
        context_tokens: int | None = None,
        uses_tools: bool = False,
        idempotency_key: bool = False,
        idem: bool = False,
        caller: str | None = None,
        labels: list[tuple[str, str, str]] | None = None,
    ) -> LogRow:
        request_index = len(self.logs)
        request_id = str(uuid.uuid5(_NAMESPACE, f"{self.seed}:{request_index}"))
        request_hash = req_hash or h or self.hash_for(f"request:{self.seed}:{request_index}")
        if req_size is None:
            req_size = (
                prompt_tokens * 4 + 220 if provider == "openai" else self.rng.randint(60, 400)
            )
        if resp_size is None:
            resp_size = (
                completion_tokens * 4 + 380
                if provider == "openai"
                else self.rng.randint(900, 2_600)
            )
        actual_prompt = prompt_tokens if 200 <= status < 300 else 0
        actual_completion = completion_tokens if 200 <= status < 300 else 0
        usage = Usage(
            prompt_tokens=actual_prompt,
            completion_tokens=actual_completion,
        )
        cost = estimate_cost(
            provider=provider,
            model=model,
            usage=usage if provider == "openai" else None,
            status=status,
            at=timestamp,
        )
        latency_ms = round(max(1.0, self.rng.lognormvariate(5.4, 0.65)), 1)
        log = LogRow(
            id=request_id,
            occurred_at=timestamp.astimezone(UTC),
            provider=provider,
            endpoint=endpoint,
            method=method,
            req_size=req_size,
            req_hash=request_hash,
            status=status,
            resp_size=resp_size,
            latency_ms=latency_ms,
            ttfb_ms=round(latency_ms * 0.3, 1),
            cost_usd=float(cost.cost_usd if cost.cost_usd > Decimal("0") else 0),
            cost_basis=cost.basis,
            pricing_version=cost.pricing_version,
            source="demo",
            origin="upstream",
            is_demo=True,
            flagged_by=[],
            caller=caller,
            model=model,
            prompt_tokens=actual_prompt,
            completion_tokens=actual_completion,
            tokens_estimated=False,
            stream=False,
            error_code=(
                "rate_limit_exceeded"
                if status == 429
                else "upstream_error"
                if status >= 500
                else None
            ),
            has_idempotency_key=idempotency_key or idem,
            context_hash=context_hash or ctx,
            context_tokens=context_tokens,
            uses_tools=uses_tools,
        )
        self.logs.append(log)
        for rule_id, role, pattern in labels or []:
            self.labels.append(
                GroundTruthLabel(
                    request_id=request_id,
                    rule_id=rule_id,
                    role=role,
                    pattern=pattern,
                )
            )
        return log

    log = add

    def chat(self, timestamp: datetime, model: str, prompt: int, completion: int, **kwargs):
        return self.add(
            timestamp,
            "openai",
            "POST",
            "/v1/chat/completions",
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            **kwargs,
        )

    def embed(self, timestamp: datetime, prompt: int, **kwargs):
        return self.add(
            timestamp,
            "openai",
            "POST",
            "/v1/embeddings",
            model="text-embedding-3-small",
            prompt_tokens=prompt,
            resp_size=33_000,
            **kwargs,
        )

    def baseline(self, count: int) -> None:
        for index in range(count):
            timestamp = self.when()
            if self.rng.random() < 0.68:
                models = ("gpt-4o-mini", "gpt-4o", "text-embedding-3-small")
                model = self.rng.choices(models, weights=(72, 16, 12))[0]
                if model == "text-embedding-3-small":
                    self.embed(
                        timestamp,
                        self.rng.randint(20, 180),
                        caller="search-api",
                    )
                else:
                    prompt_range = (1_000, 1_400) if model == "gpt-4o" else (250, 1_400)
                    completion_range = (350, 420) if model == "gpt-4o" else (20, 420)
                    self.chat(
                        timestamp,
                        model,
                        self.rng.randint(*prompt_range),
                        self.rng.randint(*completion_range),
                        caller="support-bot" if index % 2 else "report-writer",
                    )
            elif self.rng.random() < 0.82:
                self.add(
                    timestamp,
                    "stripe",
                    "GET",
                    f"/v1/customers/cus_{self.rng.getrandbits(48):012x}",
                    caller="admin-dashboard",
                )
            else:
                self.add(
                    timestamp,
                    "stripe",
                    "POST",
                    "/v1/payment_intents",
                    idempotency_key=True,
                    caller="checkout",
                )

    def finish(self) -> tuple[list[LogRow], GroundTruth]:
        self.logs.sort(key=lambda log: (log.timestamp, log.id))
        self.labels.sort(
            key=lambda label: (
                label.request_id,
                label.rule_id,
                label.role,
                label.pattern,
            )
        )
        return self.logs, GroundTruth(
            seed=self.seed,
            generator_version=GENERATOR_VERSION,
            labels=self.labels,
        )


def generate(
    seed: int = 42,
    days: int = 7,
    size: str = "small",
    start: datetime | None = None,
) -> tuple[list[LogRow], GroundTruth]:
    if days < 1 or days > 30:
        raise ValueError("days must be between 1 and 30")
    if size not in {"small", "standard"}:
        raise ValueError("size must be 'small' or 'standard'")
    if start is not None and start.utcoffset() is None:
        raise ValueError("start must include a timezone")

    start_time = start or datetime(2026, 1, 16, tzinfo=UTC)
    generator = SyntheticGenerator(seed, days, size, start_time)
    if size == "small":
        baseline_count = max(1, _SMALL_BASELINE_PER_WEEK * days // 7)
        scenario_repeats = 1
    else:
        baseline_count = min(
            _STANDARD_BASELINE_PER_WEEK * days // 7,
            _MAX_STANDARD_BASELINE,
        )
        scenario_repeats = min(days, 7)
    generator.baseline(baseline_count)
    inject_scenarios(generator, scenario_repeats)
    return generator.finish()
