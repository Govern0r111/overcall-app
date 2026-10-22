from __future__ import annotations

from fastapi import APIRouter, Depends

from ...deps import current_user
from . import (
    accuracy,
    data,
    demo,
    detection,
    health,
    ingest_keys,
    issues,
    logs,
    me,
    overview,
    providers,
    rules,
    settings,
)

health_router = health.router

# Every /v1 route requires a verified Supabase JWT.
v1_router = APIRouter(prefix="/v1", dependencies=[Depends(current_user)])
for _module in (
    me,
    overview,
    issues,
    logs,
    providers,
    settings,
    rules,
    detection,
    demo,
    data,
    accuracy,
    ingest_keys,
):
    v1_router.include_router(_module.router)

__all__ = ["health_router", "v1_router"]
