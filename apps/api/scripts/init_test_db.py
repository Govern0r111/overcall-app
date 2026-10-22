from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"


async def initialize() -> None:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        raise RuntimeError("Set TEST_DATABASE_URL to a disposable local PostgreSQL database.")
    host = urlparse(url).hostname
    if host not in {"localhost", "127.0.0.1", "host.docker.internal"}:
        raise RuntimeError("Refusing to initialize a non-local test database.")

    connection = await asyncpg.connect(url)
    try:
        async with connection.transaction():
            await connection.execute((API_ROOT / "tests" / "sql" / "00_auth_stub.sql").read_text())
            for migration in sorted(MIGRATIONS.glob("20261022*.sql")):
                await connection.execute(migration.read_text(encoding="utf-8"))
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(initialize())
