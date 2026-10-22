from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from overcall.db.models import DetectionRun, Issue, RequestLog
from overcall.db.repos.issues import IssuesRepository
from overcall.detection.base import Finding, LogRow, RuleContext
from overcall.detection.registry import DuplicateCalls
from overcall.detection.runner import DetectionRunner


def _test_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


class FailingRule:
    id = "test_failure"
    name = "Test failure"
    tier = 1
    description = "Raises to verify per-rule isolation."
    default_enabled = True
    threshold_keys: tuple[str, ...] = ()

    def detect(self, logs: Sequence[LogRow], ctx: RuleContext) -> list[Finding]:
        raise RuntimeError("intentional test failure")


def test_runner_rollback_rule_isolation_and_concurrent_replacement() -> None:
    url = _test_database_url()
    user_id = uuid4()
    user_ids = [user_id]
    old_issue_id = uuid4()
    old_run_id = uuid4()
    now = datetime.now(UTC)

    async def exercise() -> None:
        engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        """
                        insert into auth.users (id) values (:id)
                        """
                    ),
                    {"id": user_id},
                )

            async with session_factory() as session:
                session.add_all(
                    [
                        RequestLog(
                            id=uuid4(),
                            user_id=user_id,
                            source="proxy",
                            origin="upstream",
                            occurred_at=now - timedelta(seconds=5),
                            provider="openai",
                            method="POST",
                            endpoint="/v1/chat/completions",
                            status=200,
                            latency_ms=20,
                            req_size=100,
                            resp_size=200,
                            req_hash="same-request",
                            cost_usd=Decimal("0.01"),
                            cost_basis="billed",
                            pricing_version="2026-01-15",
                        ),
                        RequestLog(
                            id=uuid4(),
                            user_id=user_id,
                            source="proxy",
                            origin="upstream",
                            occurred_at=now,
                            provider="openai",
                            method="POST",
                            endpoint="/v1/chat/completions",
                            status=200,
                            latency_ms=20,
                            req_size=100,
                            resp_size=200,
                            req_hash="same-request",
                            cost_usd=Decimal("0.01"),
                            cost_basis="billed",
                            pricing_version="2026-01-15",
                        ),
                        DetectionRun(
                            id=old_run_id,
                            user_id=user_id,
                            status="succeeded",
                            is_demo_data=False,
                        ),
                        Issue(
                            id=old_issue_id,
                            user_id=user_id,
                            run_id=old_run_id,
                            rule_id="old_issue",
                            tier=1,
                            experimental=False,
                            provider="openai",
                            endpoint="/v1/chat/completions",
                            severity="info",
                            impact_kind="spend",
                            title="Existing issue",
                            summary="Existing issue",
                            explanation="Existing issue",
                            suggested_fix="Existing issue",
                            affected_count=1,
                            is_demo_data=False,
                        ),
                    ]
                )
                await session.commit()

            original_delete = IssuesRepository.delete_for_user

            async def delete_then_fail(repository: IssuesRepository) -> None:
                await original_delete(repository)
                raise RuntimeError("intentional transaction failure")

            IssuesRepository.delete_for_user = delete_then_fail
            try:
                with pytest.raises(RuntimeError, match="intentional transaction failure"):
                    await DetectionRunner(session_factory).run(user_id)
            finally:
                IssuesRepository.delete_for_user = original_delete

            async with session_factory() as session:
                assert await session.get(Issue, old_issue_id) is not None

            runner = DetectionRunner(session_factory, (FailingRule(), DuplicateCalls()))
            first_run, second_run = await asyncio.gather(
                runner.run(user_id),
                runner.run(user_id),
            )
            assert first_run.id != second_run.id
            assert first_run.rule_errors == [
                {"rule_id": "test_failure", "error_type": "RuntimeError"}
            ]
            assert first_run.request_count == 2

            async with session_factory() as session:
                issues = list(
                    (
                        await session.scalars(
                            select(Issue).where(Issue.user_id == user_id)
                        )
                    ).all()
                )
                assert len(issues) == 1
                assert issues[0].rule_id == "duplicate_calls"
                assert issues[0].run_id in {first_run.id, second_run.id}
                assert issues[0].affected_count == 1
                assert await session.get(DetectionRun, old_run_id) is not None

            first_issue = (
                issues[0].rule_id,
                issues[0].severity,
                issues[0].provider,
                issues[0].endpoint,
                issues[0].affected_count,
                issues[0].window_savings_usd,
                issues[0].projected_monthly_usd,
            )
            await runner.run(user_id)
            async with session_factory() as session:
                repeated_issue = (
                    await session.scalars(
                        select(Issue).where(Issue.user_id == user_id)
                    )
                ).one()
                assert (
                    repeated_issue.rule_id,
                    repeated_issue.severity,
                    repeated_issue.provider,
                    repeated_issue.endpoint,
                    repeated_issue.affected_count,
                    repeated_issue.window_savings_usd,
                    repeated_issue.projected_monthly_usd,
                ) == first_issue

            failed_run = await DetectionRunner(session_factory, (FailingRule(),)).run(user_id)
            assert failed_run.request_count == 2
            assert failed_run.rule_errors == [
                {"rule_id": "test_failure", "error_type": "RuntimeError"}
            ]
            async with session_factory() as session:
                assert (
                    await session.scalars(select(Issue).where(Issue.user_id == user_id))
                ).all() == []

            async with session_factory() as session:
                await session.execute(delete(RequestLog).where(RequestLog.user_id == user_id))
                session.add(
                    RequestLog(
                        id=uuid4(),
                        user_id=user_id,
                        source="proxy",
                        origin="upstream",
                        occurred_at=now,
                        provider="openai",
                        method="POST",
                        endpoint="/v1/chat/completions",
                        status=200,
                        latency_ms=20,
                        req_size=100,
                        resp_size=200,
                        req_hash="single-request",
                        cost_usd=Decimal("0.01"),
                        cost_basis="billed",
                        pricing_version="2026-01-15",
                    )
                )
                await session.commit()
            single_run = await DetectionRunner(session_factory, (DuplicateCalls(),)).run(user_id)
            assert single_run.request_count == 1
            async with session_factory() as session:
                assert (
                    await session.scalars(select(Issue).where(Issue.user_id == user_id))
                ).all() == []

            empty_user_id = uuid4()
            user_ids.append(empty_user_id)
            async with engine.begin() as connection:
                await connection.execute(
                    text("insert into auth.users (id) values (:id)"),
                    {"id": empty_user_id},
                )
            empty_run = await DetectionRunner(session_factory, (DuplicateCalls(),)).run(
                empty_user_id
            )
            assert empty_run.request_count == 0
            assert empty_run.rule_errors == []
            async with session_factory() as session:
                assert (
                    await session.scalars(
                        select(Issue).where(Issue.user_id == empty_user_id)
                    )
                ).all() == []
            async with engine.begin() as connection:
                await connection.execute(
                    text("delete from auth.users where id = :id"),
                    {"id": empty_user_id},
                )
        finally:
            async with engine.begin() as connection:
                for test_user_id in user_ids:
                    await connection.execute(
                        delete(Issue).where(Issue.user_id == test_user_id)
                    )
                    await connection.execute(
                        delete(DetectionRun).where(DetectionRun.user_id == test_user_id)
                    )
                    await connection.execute(
                        delete(RequestLog).where(RequestLog.user_id == test_user_id)
                    )
                    await connection.execute(
                        text("delete from auth.users where id = :id"),
                        {"id": test_user_id},
                    )
            await engine.dispose()

    asyncio.run(exercise())
