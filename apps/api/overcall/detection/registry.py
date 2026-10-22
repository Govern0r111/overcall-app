from __future__ import annotations

import json
from pathlib import Path

from .base import Rule
from .rules import (
    DuplicateCalls,
    MissingCache,
    ModelOveruse,
    OversizedPayload,
    RetryStorm,
    TokenBloat,
    UnbatchedCalls,
)

RULES: tuple[Rule, ...] = (
    DuplicateCalls(),
    MissingCache(),
    RetryStorm(),
    OversizedPayload(),
    UnbatchedCalls(),
    TokenBloat(),
    ModelOveruse(),
)
RULES_BY_ID: dict[str, Rule] = {rule.id: rule for rule in RULES}
RULES_PATH = Path(__file__).resolve().parents[4] / "contract" / "rules.json"

if len(RULES_BY_ID) != len(RULES):
    raise RuntimeError("Detection rule ids must be unique")


def validate_rule_catalogue() -> None:
    try:
        catalogue = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load rules contract: {RULES_PATH}") from exc
    contract_rules = catalogue.get("rules") if isinstance(catalogue, dict) else None
    if not isinstance(contract_rules, list):
        raise RuntimeError("Rules contract must contain a rules array")
    contract_by_id = {item.get("id"): item for item in contract_rules if isinstance(item, dict)}
    if set(contract_by_id) != set(RULES_BY_ID):
        raise RuntimeError("Rule registry ids do not match the contract catalogue")
    for rule_id, rule in RULES_BY_ID.items():
        entry = contract_by_id[rule_id]
        if (entry.get("name"), entry.get("tier"), entry.get("description")) != (
            rule.name,
            rule.tier,
            rule.description,
        ):
            raise RuntimeError(f"Rule registry metadata does not match contract for {rule_id}")
