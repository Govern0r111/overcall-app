from typing import Dict, Literal

from pydantic import BaseModel, Field

from .db import settings_col
from .rules import RULES

SETTINGS_ID = "app"


class Windows(BaseModel):
    short_window_s: float = Field(10, gt=0)
    long_window_s: float = Field(600, gt=0)
    retry_min_backoff_ms: float = Field(1000, gt=0)
    retry_min_attempts: int = Field(3, ge=2)
    oversized_bytes: int = Field(200_000, gt=0)
    unbatched_min_calls: int = Field(5, ge=2)
    unbatched_window_s: float = Field(5, gt=0)
    token_bloat_min_repeats: int = Field(3, ge=2)
    token_bloat_min_prompt_tokens: int = Field(1500, gt=0)
    model_overuse_max_prompt_tokens: int = Field(800, gt=0)
    model_overuse_max_completion_tokens: int = Field(300, gt=0)


class AppSettings(BaseModel):
    rules: Dict[str, bool] = Field(default_factory=lambda: {r.id: True for r in RULES})
    experimental_enabled: bool = False
    windows: Windows = Field(default_factory=Windows)
    currency: Literal["INR", "USD"] = "INR"
    usd_inr_rate: float = Field(83.5, gt=0)
    openai_upstream: Literal["mock", "real"] = "mock"


async def get_settings() -> AppSettings:
    doc = await settings_col.find_one({"_id": SETTINGS_ID}) or {}
    doc.pop("_id", None)
    s = AppSettings.model_validate(doc)
    s.rules = {r.id: s.rules.get(r.id, True) for r in RULES}
    return s


async def save_settings(s: AppSettings) -> AppSettings:
    s.rules = {r.id: s.rules.get(r.id, True) for r in RULES}
    await settings_col.replace_one({"_id": SETTINGS_ID}, s.model_dump(), upsert=True)
    return s
