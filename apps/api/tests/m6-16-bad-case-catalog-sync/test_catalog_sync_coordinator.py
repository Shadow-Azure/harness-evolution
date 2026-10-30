"""Single-flight scheduling and status aggregation for catalog sync."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_catalog_sync import (
    BadCaseCatalogSyncRepository,
    CatalogCaseRow,
)
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.jobs import JobRunRecord
from app.service.acquisition.bad_case_catalog_sync import (
    KIND,
    BadCaseCatalogSyncService,
)
from app.service.acquisition.bad_case_catalog_sync_coordinator import (
    BadCaseCatalogSyncCoordinator,
)
from app.service.jobs import JobRunner, JobSubmission
from app.utils.time import now_shanghai


class FakeJobRepository:
    """Active-job lookup stub shared by the coordinator tests."""

    def __init__(self) -> None:
        self.active: JobRunRecord | None = None

    async def find_active_kind(self, kind: str) -> JobRunRecord | None:
        return self.active


class FakeJobs:
    """Record submissions without starting the real worker loop."""

    def __init__(self) -> None:
        self.repository = FakeJobRepository()
        self.submitted: list[str] = []

    async def submit(
        self,
        *,
        kind: str,
        payload: object,
        ref_id: str | None,
        created_by: str | None,
    ) -> JobSubmission:
        self.submitted.append(kind)
        job = cast(
            JobRunRecord,
            SimpleNamespace(id=f"job-{len(self.submitted)}", status="queued"),
        )
        return JobSubmission(job=job, reused=False)


def _settings(tmp_path: Path, *, configured: bool) -> Settings:
    extra: dict[str, Any] = (
        {
            "bad_case_query_base_url": "http://query.test",
            "bad_case_query_token": SecretStr("token"),
        }
        if configured
        else {}
    )
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("coordinator-test-secret"),
        bad_case_catalog_sync_interval_seconds=0,
        **extra,
    )


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide a migrated SQLite database for coordinator state."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path / "db",
        jwt_secret=SecretStr("coordinator-db-secret"),
    )
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


def _coordinator(
    database: Database,
    settings: Settings,
) -> tuple[BadCaseCatalogSyncCoordinator, FakeJobs]:
    repository = BadCaseCatalogSyncRepository(database)
    service = BadCaseCatalogSyncService(repository, None)
    fake = FakeJobs()
    coordinator = BadCaseCatalogSyncCoordinator(
        cast(JobRunner, fake),
        repository,
        settings,
        service,
    )
    return coordinator, fake


@pytest.mark.asyncio
async def test_unavailable_reports_and_skips_trigger(
    database: Database,
    tmp_path: Path,
) -> None:
    """Without a configured endpoint the status is unavailable and no job runs."""
    coordinator, fake = _coordinator(database, _settings(tmp_path, configured=False))

    status = await coordinator.status()
    trigger = await coordinator.trigger("scheduler")

    assert status.status == "unavailable"
    assert status.synced == 0
    assert trigger.status == "unavailable"
    assert fake.submitted == []


@pytest.mark.asyncio
async def test_active_job_is_skipped(database: Database, tmp_path: Path) -> None:
    """A queued or running catalog job prevents a second submission."""
    coordinator, fake = _coordinator(database, _settings(tmp_path, configured=True))
    fake.repository.active = cast(
        JobRunRecord,
        SimpleNamespace(id="job-active", status="running"),
    )

    trigger = await coordinator.trigger("scheduler")
    status = await coordinator.status()

    assert trigger.status == "skipped"
    assert trigger.job_id == "job-active"
    assert fake.submitted == []
    assert status.status == "running"


@pytest.mark.asyncio
async def test_start_triggers_once_and_stops(database: Database, tmp_path: Path) -> None:
    """Startup submits one job immediately when the previous run is finished."""
    coordinator, fake = _coordinator(database, _settings(tmp_path, configured=True))

    await coordinator.start()
    await coordinator.stop()

    assert fake.submitted == [KIND]


@pytest.mark.asyncio
async def test_reconcile_marks_interrupted_run(database: Database, tmp_path: Path) -> None:
    """A running row without an active job is interrupted after a restart."""
    repository = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    await repository.initialize(now)
    await repository.mark_running(now)
    coordinator, _ = _coordinator(database, _settings(tmp_path, configured=True))

    await coordinator.reconcile()

    state = await repository.get_state()
    assert state is not None
    assert state.status == "failed"
    assert state.last_error == "BAD_CASE_CATALOG_SYNC_INTERRUPTED"


@pytest.mark.asyncio
async def test_status_aggregates_counts(database: Database, tmp_path: Path) -> None:
    """Status reports the local row count, cursor, and upstream remainder."""
    repository = BadCaseCatalogSyncRepository(database)
    now = now_shanghai()
    await repository.initialize(now)
    await repository.mark_running(now)
    await repository.commit_page(
        [
            CatalogCaseRow(
                bad_case_id=case_id,
                bad_case_session_id=f"session-{case_id}",
                bad_case_type="self",
                object_name="deep-research",
                object_type="skill",
                object_version="v1",
                bad_case_agent_id=None,
                title=f"case {case_id}",
                description="description",
                meta_data=None,
                source="test",
                created_at=now,
                updated_at=now,
            )
            for case_id in (1, 2, 3)
        ],
        last_bad_case_id=3,
        pending_count=2,
        now=now,
    )
    await repository.mark_idle(now, pending=2)
    coordinator, _ = _coordinator(database, _settings(tmp_path, configured=True))

    status = await coordinator.status()

    assert status.synced == 3
    assert status.unsynced == 2
    assert status.last_bad_case_id == 3
    assert status.status == "idle"
    assert status.last_run_at is not None
