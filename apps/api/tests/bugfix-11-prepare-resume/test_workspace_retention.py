"""Interrupted runs keep their workspace until recovery finishes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.models.jobs import JobRunRecord
from app.service.evolution.advance import EvolutionJobLifecycle

NOW = datetime(2026, 11, 21, 9, 30, tzinfo=UTC)


class FakeRuns:
    """Return one interrupted run in the summary projection."""

    async def list_summaries(self) -> tuple[Any, ...]:
        """Expose the interrupted run exactly as the mobile list projection does."""
        return (SimpleNamespace(run=SimpleNamespace(id="run-interrupted", status="interrupted")),)


class FakeWorkspaces:
    """Capture the active run ids passed to retention cleanup."""

    supports_candidate_lifecycle = True

    def __init__(self) -> None:
        """Start with no cleanup calls."""
        self.active: set[str] | None = None

    def cleanup_workspaces(
        self,
        *,
        active_run_ids: set[str],
        keep: int = 20,
    ) -> tuple[Path, ...]:
        """Record the protected runs and delete nothing."""
        self.active = set(active_run_ids)
        return ()


def _job() -> JobRunRecord:
    """Build one interrupted prepare job identity."""
    return JobRunRecord(
        id="job-interrupted",
        kind="evolution_prepare",
        ref_id="run-interrupted",
        status="interrupted",
        progress=0.5,
        executor="local",
        external_job_id=None,
        attempt=1,
        payload={"runId": "run-interrupted"},
        result=None,
        error="process restarted",
        created_by=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_interrupted_run_workspace_is_retained() -> None:
    """Workspace cleanup must not delete a run that startup recovery will resume."""
    workspaces = FakeWorkspaces()
    lifecycle = EvolutionJobLifecycle(
        FakeRuns(),  # type: ignore[arg-type]
        SimpleNamespace(),
        workspaces,
    )

    await lifecycle.on_terminal(_job())

    assert workspaces.active == {"run-interrupted"}
