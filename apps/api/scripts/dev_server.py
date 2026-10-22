"""Dev-only API server for exercising the API against a fixed local user.

This deliberately bypasses Supabase JWT auth and must never be deployed. It refuses
non-local databases and binds to loopback. Usage (from apps/api):
    set DEV_DATABASE_URL=postgresql://postgres@127.0.0.1:53697/overcall_test
    python scripts/dev_server.py
Then open http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import uvicorn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overcall.config import Settings  # noqa: E402
from overcall.deps import UserContext, current_user  # noqa: E402
from overcall.main import create_app  # noqa: E402

DEV_USER = UUID("00000000-0000-4000-8000-00000000d3a0")
DEV_PEPPER = "local-dev-only-pepper-0123456789abcdef"


def main() -> None:
    url = os.getenv("DEV_DATABASE_URL", "")
    host = urlsplit(url).hostname
    if host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("DEV_DATABASE_URL must point at a local database.")
    async_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    async def ensure_user() -> None:
        engine = create_async_engine(async_url, connect_args={"statement_cache_size": 0})
        async with engine.begin() as conn:
            await conn.execute(
                text("insert into auth.users (id) values (:id) on conflict do nothing"),
                {"id": DEV_USER},
            )
        await engine.dispose()

    asyncio.run(ensure_user())
    app = create_app(
        Settings(
            app_env="development",
            database_url=async_url,
            release="dev",
            cors_origins="http://localhost:5173,http://127.0.0.1:5173",
            ingest_key_pepper=DEV_PEPPER,
        )
    )

    async def dev_user() -> UserContext:
        return UserContext(user_id=DEV_USER, email="dev@overcall.local")

    app.dependency_overrides[current_user] = dev_user
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
