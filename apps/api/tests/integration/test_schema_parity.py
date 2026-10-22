from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from sqlalchemy import DateTime, Float, Numeric, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from overcall.db.models import SQLModel

PUBLIC_SCHEMAS = (None, "public")


def _test_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


def test_postgres_schema_matches_sqlmodel_tables() -> None:
    url = _test_database_url()

    async def inspect_schema() -> dict[str, list[dict[str, Any]]]:
        engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
        try:
            async with engine.connect() as connection:

                def read_schema(sync_connection):
                    inspector = inspect(sync_connection)
                    assert set(inspector.get_table_names(schema="public")) == {
                        table_name
                        for table_name, table in SQLModel.metadata.tables.items()
                        if table.schema in PUBLIC_SCHEMAS
                    }
                    return {
                        table_name: inspector.get_columns(table_name, schema="public")
                        for table_name, table in SQLModel.metadata.tables.items()
                        if table.schema in PUBLIC_SCHEMAS
                    }

                return await connection.run_sync(read_schema)
        finally:
            await engine.dispose()

    actual = asyncio.run(inspect_schema())
    expected_tables = {
        table_name
        for table_name, table in SQLModel.metadata.tables.items()
        if table.schema in PUBLIC_SCHEMAS
    }
    assert expected_tables, "no public tables were discovered"
    assert set(actual) == expected_tables

    for table_name, table in SQLModel.metadata.tables.items():
        if table.schema not in PUBLIC_SCHEMAS:
            continue
        actual_columns = {column["name"]: column for column in actual[table_name]}
        assert set(actual_columns) == set(table.columns.keys()), table_name
        for column_name, column in table.columns.items():
            observed = actual_columns[column_name]
            assert observed["nullable"] == column.nullable, (
                f"{table_name}.{column_name} nullability"
            )
            assert observed["type"]._type_affinity is column.type._type_affinity, (
                f"{table_name}.{column_name} type: {observed['type']} != {column.type}"
            )
            if isinstance(column.type, Numeric) and not isinstance(column.type, Float):
                assert observed["type"].precision == column.type.precision
                assert observed["type"].scale == column.type.scale
            if isinstance(column.type, DateTime):
                assert observed["type"].timezone == column.type.timezone
            if isinstance(column.type, Float) and column.type.precision == 24:
                assert type(observed["type"]).__name__ == "REAL"
            elif isinstance(column.type, Float):
                assert observed["type"].precision == column.type.precision


def test_rls_is_enabled_without_data_api_policies_or_grants() -> None:
    url = _test_database_url()
    expected_tables = [
        table_name
        for table_name, table in SQLModel.metadata.tables.items()
        if table.schema in PUBLIC_SCHEMAS
    ]
    assert expected_tables, "no public tables were discovered"

    async def check_security() -> None:
        engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
        try:
            async with engine.connect() as connection:
                for table_name in expected_tables:
                    row = (
                        await connection.execute(
                            text(
                                """
                                select
                                    c.relrowsecurity,
                                    has_table_privilege(
                                        'anon',
                                        format('%I.%I', n.nspname, c.relname),
                                        'select'
                                    ),
                                    has_table_privilege(
                                        'authenticated',
                                        format('%I.%I', n.nspname, c.relname),
                                        'select'
                                    )
                                from pg_class c
                                join pg_namespace n on n.oid = c.relnamespace
                                where n.nspname = 'public' and c.relname = :table_name
                                """
                            ),
                            {"table_name": table_name},
                        )
                    ).one()
                    assert row[0] is True, f"{table_name} must have RLS enabled"
                    assert row[1] is False, f"anon must not read {table_name}"
                    assert row[2] is False, f"authenticated must not read {table_name}"
                    policy_count = (
                        await connection.execute(
                            text("""
                                select count(*)
                                from pg_policies
                                where schemaname = 'public' and tablename = :table_name
                                """),
                            {"table_name": table_name},
                        )
                    ).scalar_one()
                    assert policy_count == 0, f"{table_name} must have no policies"
        finally:
            await engine.dispose()

    asyncio.run(check_security())
