from typing import Literal

from pydantic import BaseModel, ConfigDict


class GroundTruthLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    rule_id: Literal[
        "duplicate_calls",
        "missing_cache",
        "retry_storm",
        "oversized_payload",
        "unbatched_calls",
        "token_bloat",
        "model_overuse",
    ]
    role: Literal["positive", "hard_negative"]
    pattern: str


class GroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    generator_version: str
    labels: list[GroundTruthLabel]

    def request_ids(self, rule_id: str, role: str = "positive") -> set[str]:
        return {
            label.request_id
            for label in self.labels
            if label.rule_id == rule_id and label.role == role
        }

    def counts(self) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for label in self.labels:
            counts = result.setdefault(label.rule_id, {"positive": 0, "hard_negative": 0})
            counts[label.role] += 1
        return result
