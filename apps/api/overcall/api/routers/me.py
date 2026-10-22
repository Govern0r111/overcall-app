from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings
from ...db.models import IngestKey, RequestLog
from ...db.models import Issue as IssueModel
from ...db.repos.settings import SettingsRepository
from ...deps import UserContext, current_user, get_app_settings, get_session
from ..schemas import Me

router = APIRouter(tags=["account"])


@router.get("/me", response_model=Me)
async def get_me(
    user: UserContext = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    env: Settings = Depends(get_app_settings),
) -> Me:
    settings = await SettingsRepository(session, user.user_id).get_or_create()
    active_keys = await session.scalar(
        select(func.count())
        .select_from(IngestKey)
        .where(IngestKey.user_id == user.user_id, IngestKey.revoked_at.is_(None))
    )
    traffic = (
        await session.execute(
            select(RequestLog.source, func.count(), func.max(RequestLog.occurred_at))
            .where(RequestLog.user_id == user.user_id)
            .group_by(RequestLog.source)
        )
    ).all()
    counts = {source: count for source, count, _ in traffic}
    last_proxy = next((last for source, _, last in traffic if source == "proxy"), None)
    issue_count = await session.scalar(
        select(func.count())
        .select_from(IssueModel)
        .where(IssueModel.user_id == user.user_id, IssueModel.experimental.is_(False))
    )
    await session.commit()

    proxy, demo = counts.get("proxy", 0), counts.get("demo", 0)
    if proxy:
        status = "receiving_traffic"
    elif demo:
        status = "demo_only"
    elif active_keys:
        status = "waiting_for_traffic"
    else:
        status = "no_key"
    return Me(
        id=user.user_id,
        email=user.email,
        created_at=settings.created_at,
        proxy_status=status,
        last_request_at=last_proxy,
        issue_count=issue_count or 0,
        is_demo_data=proxy == 0 and demo > 0,
        has_data=(proxy + demo) > 0,
        real_upstream_available=env.allow_real_upstream,
    )
