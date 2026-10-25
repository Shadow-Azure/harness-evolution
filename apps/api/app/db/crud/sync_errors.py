"""Persistence of sanitized normalization issues on a sync run."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.db.base import Database
from app.db.models.domain import sync_runs
from app.service.acquisition.normalize import ParsedIssue


async def append_normalization_issues(
    database: Database,
    sync_run_id: str,
    issues: Sequence[ParsedIssue],
) -> None:
    """Append stable issue fields to one sync run in a write transaction."""
    if not issues:
        return
    async with database.transaction() as session:
        existing = (
            await session.execute(
                select(sync_runs.c.errors).where(sync_runs.c.id == sync_run_id),
            )
        ).scalar_one_or_none()
        if existing is None:
            raise ValueError("sync run does not exist")
        errors = list(existing)
        errors.extend(issue.as_sync_error() for issue in issues)
        await session.execute(
            sync_runs.update().where(sync_runs.c.id == sync_run_id).values(errors=errors),
        )
