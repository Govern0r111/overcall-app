from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import DetectionRun, Issue, RequestLog
from ...deps import UserContext, current_user, get_session
from ...errors import OvercallError

router = APIRouter(tags=["data"])

DELETE_PHRASE = "delete my data"


@router.delete("/data", status_code=204)
async def delete_all_data(
    body: dict[str, Any] | None = Body(default=None),
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if not isinstance(body, dict) or body.get("confirm") != DELETE_PHRASE:
        raise OvercallError(
            "confirmation_required",
            400,
            f'Type "{DELETE_PHRASE}" to confirm.',
        )
    # Issue requests cascade from issues and logs. Ingest keys and settings are kept.
    await session.execute(delete(Issue).where(Issue.user_id == user.user_id))
    await session.execute(delete(DetectionRun).where(DetectionRun.user_id == user.user_id))
    await session.execute(delete(RequestLog).where(RequestLog.user_id == user.user_id))
    await session.commit()
    return Response(status_code=204)
