"""The public blocked-stage schema and the attribution retry handoff."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from app.config import DatabaseDialect, Settings
from app.db.crud.evolution import EvolutionRepository
from app.db.models.jobs import JobRunRecord
from app.main import create_app
from app.service.evolution.retry import EvolutionRetryService
from tests.attribution.support import NOW, RUN_ID, Harness


def test_run_detail_schema_exposes_attribution_as_a_blocked_stage() -> None:
    """blockedStage is the only place the blocked phase is published to clients."""
    schema = create_app(Settings(db_dialect=DatabaseDialect.SQLITE)).openapi()
    blocked = schema["components"]["schemas"]["EvolutionRunDetail"]["properties"]["blockedStage"]

    assert {"enum": ["patch", "push", "eval", "attribution"], "type": "string"} in blocked["anyOf"]


class FakeJobs:
    """Capture the durable job submissions a retry decides to schedule."""

    def __init__(self) -> None:
        self.submissions: list[tuple[str, dict[str, Any], str | None, str | None]] = []

    async def submit(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> SimpleNamespace:
        """Record one submission and mimic the queue's accepted view."""
        self.submissions.append((kind, payload, ref_id, created_by))
        return SimpleNamespace(id="job-retry", reused=False)


def retry_job() -> JobRunRecord:
    """Build the durable retry job row the handler reads."""
    return JobRunRecord(
        id="job-retry",
        kind="evolution_retry",
        ref_id=RUN_ID,
        status="running",
        progress=0.0,
        executor="local",
        external_job_id=None,
        attempt=1,
        payload={"runId": RUN_ID, "automatic": False},
        result=None,
        error=None,
        created_by=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
        updated_at=NOW,
    )


async def test_retry_of_an_attribution_block_resumes_and_schedules_prepare(
    attribution_harness: Harness,
) -> None:
    """Attribution has no iteration state, so retry re-enters the prepare stage."""
    repository = EvolutionRepository(attribution_harness.database)
    await repository.mark_blocked(
        RUN_ID,
        stage="attribution",
        message="attribution failed",
        error_stage="prepare",
    )
    jobs = FakeJobs()
    service = EvolutionRetryService(
        repository,
        cast(Any, object()),
        cast(Any, jobs),
    )

    result = await service.handle(retry_job())

    assert result["resumed"] is True
    assert result["stage"] == "attribution"
    assert result["scheduled"] == "evolution_prepare"
    assert jobs.submissions == [("evolution_prepare", {"runId": RUN_ID}, RUN_ID, None)]
    resumed = await repository.get_run(RUN_ID)
    assert resumed is not None
    assert resumed.status == "running"
    assert resumed.blocked_stage is None
