"""Tenant-scoped database repositories."""

from .issues import IssuesRepository
from .logs import LogsRepository
from .runs import RunsRepository

__all__ = ["IssuesRepository", "LogsRepository", "RunsRepository"]
