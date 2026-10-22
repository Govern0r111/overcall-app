from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..config import Settings


def create_database_engine(settings: Settings) -> AsyncEngine | None:
    if settings.database_url is None:
        return None
    url = settings.database_url.get_secret_value()
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("DATABASE_URL must use PostgreSQL with the asyncpg driver")

    return create_async_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args={
            "statement_cache_size": 0,
            "ssl": "require" if settings.database_ssl else False,
        },
    )
