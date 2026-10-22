from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import UserSettings
from ...db.repos.settings import SettingsRepository, effective_rules, effective_thresholds
from ...deps import UserContext, current_user, get_app_settings, get_runner, get_session
from ...detection.registry import RULES_BY_ID
from ...detection.runner import DetectionRunner
from ...detection.thresholds import Thresholds
from ...errors import OvercallError
from ..runs import rerun_detection
from ..schemas import SettingsIn, SettingsOut

router = APIRouter(tags=["settings"])

DEFAULT_RATE = 83.5


def settings_to_schema(row: UserSettings) -> SettingsOut:
    return SettingsOut(
        currency=row.currency,
        usd_inr_rate=float(row.usd_inr_rate),
        rules_enabled=effective_rules(row),
        tier3_enabled=row.tier3_enabled,
        thresholds=effective_thresholds(row),
        upstream_mode=row.upstream_mode,
        confirm_real_upstream=False,
        retention_days=row.retention_days,
        updated_at=row.updated_at,
    )


def _validation_error(fields: list[dict[str, str]]) -> OvercallError:
    return OvercallError("validation_error", 422, "Some fields are invalid.", {"fields": fields})


def _validate(body: SettingsIn, env: Settings) -> Thresholds:
    fields: list[dict[str, str]] = []
    for rule_id in body.rules_enabled:
        if rule_id not in RULES_BY_ID:
            fields.append({"path": f"rules_enabled.{rule_id}", "message": "Unknown rule."})
    thresholds: Thresholds | None = None
    try:
        thresholds = Thresholds.model_validate(body.thresholds)
    except ValidationError as exc:
        for item in exc.errors():
            path = ".".join(["thresholds", *(str(part) for part in item.get("loc", ()))])
            fields.append({"path": path, "message": str(item["msg"]).removeprefix("Value error, ")})
    if fields:
        raise _validation_error(fields)
    assert thresholds is not None

    if body.upstream_mode == "real":
        if not env.allow_real_upstream:
            raise OvercallError(
                "real_upstream_disabled",
                403,
                "Real upstream mode is turned off on this server.",
            )
        if not body.confirm_real_upstream:
            raise OvercallError(
                "confirmation_required",
                400,
                "Confirm that you want to send traffic to the real provider.",
            )
    return thresholds


@router.get("/settings", response_model=SettingsOut)
async def get_settings(
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SettingsOut:
    row = await SettingsRepository(session, user.user_id).get_or_create()
    await session.commit()
    return settings_to_schema(row)


@router.put("/settings", response_model=SettingsOut)
async def put_settings(
    body: SettingsIn,
    background: BackgroundTasks,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    env: Settings = Depends(get_app_settings),
    runner: DetectionRunner = Depends(get_runner),
) -> SettingsOut:
    thresholds = _validate(body, env)
    row = await SettingsRepository(session, user.user_id).get_or_create()
    merged_rules: dict[str, Any] = dict(effective_rules(row))
    merged_rules.update(body.rules_enabled)

    row.currency = body.currency
    row.usd_inr_rate = body.usd_inr_rate
    row.rules_enabled = merged_rules
    row.tier3_enabled = body.tier3_enabled
    row.thresholds = thresholds.model_dump(mode="json")
    row.upstream_mode = body.upstream_mode
    row.retention_days = body.retention_days
    row.updated_at = datetime.now(UTC)
    await session.commit()
    result = settings_to_schema(row)
    await rerun_detection(session, runner, background, user.user_id)
    return result


@router.post("/settings/reset", response_model=SettingsOut)
async def reset_settings(
    background: BackgroundTasks,
    body: dict[str, Any] | None = Body(default=None),
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    env: Settings = Depends(get_app_settings),
    runner: DetectionRunner = Depends(get_runner),
) -> SettingsOut:
    if not isinstance(body, dict) or body.get("confirm") is not True:
        raise OvercallError("confirmation_required", 400, "Confirm this action before continuing.")
    row = await SettingsRepository(session, user.user_id).get_or_create()
    row.currency = "INR"
    row.usd_inr_rate = DEFAULT_RATE
    row.rules_enabled = {}
    row.tier3_enabled = False
    row.thresholds = {}
    row.upstream_mode = "mock"
    row.retention_days = env.log_retention_default_days
    row.updated_at = datetime.now(UTC)
    await session.commit()
    result = settings_to_schema(row)
    await rerun_detection(session, runner, background, user.user_id)
    return result
