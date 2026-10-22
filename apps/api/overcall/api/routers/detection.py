from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import DetectionRun
from ...deps import UserContext, current_user, get_runner, get_session
from ...detection.runner import DetectionRunner
from ..runs import rerun_detection
from ..schemas import RunSummary

router = APIRouter(tags=["detection"])


def run_to_summary(run: DetectionRun) -> RunSummary:
    return RunSummary(
        run_id=run.id,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        request_count=run.request_count,
        issue_counts={key: int(value) for key, value in (run.issue_counts or {}).items()},
        rule_errors=list(run.rule_errors or []),
        duration_ms=run.duration_ms,
    )


@router.post("/detection/run", response_model=RunSummary)
async def start_run(
    response: Response,
    background: BackgroundTasks,
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    runner: DetectionRunner = Depends(get_runner),
) -> RunSummary:
    run_id, run = await rerun_detection(session, runner, background, user.user_id)
    if run is None:
        response.status_code = 202
        return RunSummary(run_id=UUID(str(run_id)), status="running")
    return run_to_summary(run)


@router.get("/detection/runs/latest", response_model=RunSummary)
async def latest_run(
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> RunSummary:
    run = await session.scalar(
        select(DetectionRun)
        .where(DetectionRun.user_id == user.user_id)
        .order_by(DetectionRun.started_at.desc(), DetectionRun.id)
        .limit(1)
    )
    if run is None:
        return RunSummary(run_id=None, status="none")
    return run_to_summary(run)
