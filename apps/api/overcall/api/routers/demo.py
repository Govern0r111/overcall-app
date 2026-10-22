from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import RequestLog
from ...db.repos.settings import SettingsRepository
from ...deps import UserContext, current_user, get_runner, get_session
from ...detection.runner import DetectionRunner
from ...synthetic.generator import generate
from ..runs import rerun_detection
from ..schemas import DemoLoadIn, DemoLoadOut

router = APIRouter(tags=["demo"])

_LOG_FIELDS = (
    "occurred_at",
    "provider",
    "method",
    "endpoint",
    "status",
    "latency_ms",
    "ttfb_ms",
    "req_size",
    "resp_size",
    "req_hash",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "cached_prompt_tokens",
    "tokens_estimated",
    "stream",
    "context_hash",
    "context_tokens",
    "uses_tools",
    "list_limit",
    "items_returned",
    "has_idempotency_key",
    "caller",
    "cost_basis",
    "pricing_version",
    "error_code",
)


@router.post("/demo/load", response_model=DemoLoadOut)
async def load_demo(
    body: DemoLoadIn,
    background: BackgroundTasks,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    runner: DetectionRunner = Depends(get_runner),
) -> DemoLoadOut:
    # The generated window ends now so it falls inside the detection lookback.
    start = datetime.now(UTC).replace(microsecond=0) - timedelta(days=body.days)
    generated, _truth = generate(seed=body.seed, days=body.days, size="small", start=start)

    await SettingsRepository(session, user.user_id).get_or_create()
    await session.execute(
        delete(RequestLog).where(RequestLog.user_id == user.user_id, RequestLog.source == "demo")
    )
    rows = []
    for item in generated:
        record = item.to_record()
        rows.append(
            RequestLog(
                id=uuid4(),
                user_id=user.user_id,
                source="demo",
                origin=record["origin"],
                cost_usd=Decimal(str(record["cost_usd"])),
                **{field: record[field] for field in _LOG_FIELDS},
            )
        )
    session.add_all(rows)
    await session.commit()
    await rerun_detection(session, runner, background, user.user_id)
    return DemoLoadOut(inserted=len(rows))


@router.delete("/demo", status_code=204)
async def delete_demo(
    background: BackgroundTasks,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    runner: DetectionRunner = Depends(get_runner),
) -> Response:
    await session.execute(
        delete(RequestLog).where(RequestLog.user_id == user.user_id, RequestLog.source == "demo")
    )
    await session.commit()
    await rerun_detection(session, runner, background, user.user_id)
    return Response(status_code=204)
