from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

THRESHOLDS_PATH = Path(__file__).resolve().parents[4] / "contract" / "thresholds.json"


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    short_window_s: float = Field(default=10, ge=1, le=300)
    long_window_s: float = Field(default=600, ge=60, le=3600)
    retry_min_backoff_ms: float = Field(default=1000, ge=100, le=10_000)
    retry_min_attempts: int = Field(default=3, ge=2, le=10)
    oversized_bytes: int = Field(default=200_000, ge=10_000, le=5_000_000)
    unbatched_min_calls: int = Field(default=5, ge=2, le=100)
    unbatched_window_s: float = Field(default=5, ge=1, le=60)
    token_bloat_min_repeats: int = Field(default=3, ge=2, le=50)
    token_bloat_min_context_tokens: int = Field(default=1024, ge=256, le=32_000)
    model_overuse_max_prompt_tokens: int = Field(default=800, ge=50, le=8_000)
    model_overuse_max_completion_tokens: int = Field(default=300, ge=10, le=4_000)
    model_overuse_min_calls: int = Field(default=10, ge=3, le=1_000)

    @model_validator(mode="after")
    def validate_windows(self) -> Thresholds:
        if self.long_window_s <= self.short_window_s:
            raise ValueError("long_window_s must be greater than short_window_s")
        return self


def threshold_contract() -> dict[str, Any]:
    try:
        value = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load thresholds contract: {THRESHOLDS_PATH}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("thresholds"), dict):
        raise RuntimeError("Thresholds contract must contain a thresholds object")
    return value["thresholds"]


def validate_contract_defaults() -> None:
    contract = threshold_contract()
    expected = Thresholds().model_dump()
    if set(contract) != set(expected):
        raise RuntimeError("Thresholds contract keys do not match Thresholds model fields")
    schema = Thresholds.model_json_schema()
    for key, item in contract.items():
        if item.get("default") != expected[key]:
            raise RuntimeError(f"Threshold default for {key} does not match the contract")
        bounds = schema["properties"][key]
        if item.get("min") != bounds.get("minimum") or item.get("max") != bounds.get("maximum"):
            raise RuntimeError(f"Threshold bounds for {key} do not match the contract")
