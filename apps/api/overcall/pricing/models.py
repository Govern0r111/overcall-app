from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Provider = Literal["openai", "stripe", "aws"]
CostBasis = Literal["billed", "estimated", "modelled"]


class ModelPrice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tier: Literal["low", "high"]
    input_per_1m: Decimal = Field(ge=0)
    cached_input_per_1m: Decimal = Field(ge=0)
    output_per_1m: Decimal = Field(ge=0)


class BatchEquivalent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method: str = Field(min_length=1)
    discount: Decimal = Field(ge=0, le=1)
    basis: str = Field(min_length=1)
    fix: str = Field(min_length=1)


class PricingFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    version: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    effective_from: datetime
    retrieved_at: date
    source_url: str = Field(min_length=1)
    currency: Literal["USD"]
    models: dict[str, ModelPrice]
    default_model: str | None
    per_request_overhead_usd: Decimal = Field(ge=0)
    failed_request_overhead_usd: Decimal = Field(ge=0)
    chat_endpoints: list[str]
    deterministic_post_endpoints: list[str]
    downgrade_map: dict[str, str]
    batch_equivalents: dict[str, BatchEquivalent]
    supported: bool = True
    legacy: dict[str, object] = Field(default_factory=dict)

    @field_validator("effective_from")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("effective_from must include a UTC offset")
        return value

    @model_validator(mode="after")
    def validate_model_catalogue(self) -> PricingFile:
        if self.provider == "openai" and self.supported and not self.models:
            raise ValueError("supported providers must include at least one priced model")
        if self.models and self.default_model not in self.models:
            raise ValueError("default_model must be present in models")
        if not self.models and self.default_model is not None:
            raise ValueError("default_model must be null when there are no models")
        for source, target in self.downgrade_map.items():
            if source not in self.models or target not in self.models:
                raise ValueError(f"downgrade_map references an unknown model: {source} -> {target}")
        return self


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    cached_prompt_tokens: int = Field(default=0)
    tokens_estimated: bool = False


class CostResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cost_usd: Decimal
    basis: CostBasis
    pricing_version: str
    fallback_used: bool
    supported: bool = True
