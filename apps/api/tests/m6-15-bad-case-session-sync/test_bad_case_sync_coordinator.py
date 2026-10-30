"""Single-flight scheduling semantics for bad-case root sync."""

# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type,assignment"

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.db.crud.bad_case_sync import BadCaseRootSyncStats
from app.service.acquisition.bad_case_sync_coordinator import (
    KIND,
    BadCaseRootSyncCoordinator,
)
from app.utils.time import now_shanghai


class FakeRepository:
    def __init__(self, *, candidates: int = 1, stats: BadCaseRootSyncStats | None = None):
        self.candidates = candidates
        self.stats_value = stats or BadCaseRootSyncStats(
            total=1,
            synced=0,
            syncing=0,
            failed=0,
        )
        self.last_run = None
        self.error = None

    async def count_candidates(self, now: datetime) -> int:
        return self.candidates

    async def stats(self) -> BadCaseRootSyncStats:
        return self.stats_value

    async def last_run_at(self):
        return self.last_run

    async def last_error(self):
        return self.error


class FakeJobRepository:
    def __init__(self, active=None):
        self.active = active

    async def find_active_kind(self, kind: str):
        assert kind == KIND
        return self.active


class FakeJobs:
    def __init__(self, active=None):
        self.repository = FakeJobRepository(active)
        self.submitted: list[dict[str, object]] = []
        self.submission = SimpleNamespace(
            job=SimpleNamespace(id="job-1"),
            reused=False,
        )

    async def submit(self, **kwargs):
        self.submitted.append(kwargs)
        return self.submission


def _settings(**overrides) -> Settings:
    values = {
        "jwt_secret": SecretStr("coordinator-test-secret"),
        "session_query_base_url": "http://query.test",
        "session_query_token": SecretStr("token"),
        "bad_case_sync_interval_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_trigger_is_unavailable_without_query_service() -> None:
    jobs = FakeJobs()
    coordinator = BadCaseRootSyncCoordinator(
        jobs,
        FakeRepository(),
        _settings(session_query_base_url=None),
    )

    result = await coordinator.trigger("scheduler")

    assert result.status == "unavailable"
    assert jobs.submitted == []


@pytest.mark.asyncio
async def test_trigger_skips_while_a_job_is_active() -> None:
    active = SimpleNamespace(id="active-job", status="running")
    jobs = FakeJobs(active=active)
    coordinator = BadCaseRootSyncCoordinator(
        jobs,
        FakeRepository(),
        _settings(),
    )

    result = await coordinator.trigger("scheduler")

    assert result.status == "skipped"
    assert result.job_id == "active-job"
    assert jobs.submitted == []


@pytest.mark.asyncio
async def test_trigger_is_idle_when_no_candidates() -> None:
    jobs = FakeJobs()
    coordinator = BadCaseRootSyncCoordinator(
        jobs,
        FakeRepository(candidates=0),
        _settings(),
    )

    result = await coordinator.trigger("scheduler")

    assert result.status == "idle"
    assert jobs.submitted == []


@pytest.mark.asyncio
async def test_trigger_submits_one_fixed_ref_job() -> None:
    jobs = FakeJobs()
    coordinator = BadCaseRootSyncCoordinator(
        jobs,
        FakeRepository(),
        _settings(),
    )

    result = await coordinator.trigger("scheduler")

    assert result.status == "queued"
    assert result.job_id == "job-1"
    assert jobs.submitted[0]["kind"] == KIND
    assert jobs.submitted[0]["ref_id"] == KIND
    assert jobs.submitted[0]["created_by"] is None


@pytest.mark.asyncio
async def test_status_unavailable_has_no_stats() -> None:
    coordinator = BadCaseRootSyncCoordinator(
        FakeJobs(),
        FakeRepository(),
        _settings(session_query_base_url=None),
    )

    status = await coordinator.status()

    assert status.status == "unavailable"
    assert status.total == 1


@pytest.mark.asyncio
async def test_status_reports_active_running_job_and_counts() -> None:
    active = SimpleNamespace(id="job-1", status="running")
    repository = FakeRepository(
        stats=BadCaseRootSyncStats(total=10, synced=4, syncing=1, failed=2),
    )
    repository.last_run = now_shanghai()
    repository.error = "SESSION_QUERY_TIMEOUT"
    coordinator = BadCaseRootSyncCoordinator(
        FakeJobs(active=active),
        repository,
        _settings(),
    )

    status = await coordinator.status()

    assert status.status == "running"
    assert status.total == 10
    assert status.synced == 4
    assert status.unsynced == 6
    assert status.syncing == 1
    assert status.failed == 2
    assert status.last_error == "SESSION_QUERY_TIMEOUT"

