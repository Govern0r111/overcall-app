from __future__ import annotations

from fastapi import APIRouter

from ...detection.registry import RULES
from ..schemas import RuleInfo

router = APIRouter(tags=["rules"])


@router.get("/rules", response_model=list[RuleInfo])
async def list_rules() -> list[RuleInfo]:
    return [
        RuleInfo(
            id=rule.id,
            name=rule.name,
            tier=rule.tier,
            description=rule.description,
            default_enabled=rule.default_enabled,
            threshold_keys=list(rule.threshold_keys),
        )
        for rule in RULES
    ]
