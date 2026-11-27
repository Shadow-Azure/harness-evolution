"""Run-level evaluations: storage, polling, and the held-out test-set final."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.jobs import JobRunRecord
from app.service.evolution.apply_final import EvolutionFinalizeService
from app.service.evolution.engine.contracts import EvalGatewayConfig
from app.service.evolution.eval_poller import EvolutionEvalPoller, EvolutionEvalSubmitter
from app.third_party_api.eval_gateway.fake import FakeEvalGateway
from app.third_party_api.git.workspace import PreparedWorkspace

SH = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 25, 10, 0, tzinfo=SH)
RUN_ID = "run-evaluations"


@pytest_asyncio.fixture
async def state(tmp_path: Path) -> AsyncIterator[tuple[Any, EvolutionRepository]]:
    """Migrated SQLite state with one running full-mode run."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("bugfix-63-evaluations-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    await repository.create_run(
        {
            "id": RUN_ID,
            "title": "run evaluations",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {"mode": "fake", "primaryMetricKey": "resolved_rate"},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": "https://example.invalid/repo.git",
            "sub_dir": "skills/deep-research",
            "base_ref": "v2.0.0",
            "base_commit": "a" * 40,
            "branch_name": "evo/20261125-run-evaluations",
            "repo_path": str(tmp_path / "repo"),
            "workspace_path": str(tmp_path / "workspace"),
            "status": "running",
            "progress_unit": 5,
            "stats": {},
            "created_by": None,
            "created_at": NOW,
        },
    )
    try:
        yield database, repository
    finally:
        await database.dispose()


class WorkspaceDouble:
    """Record final branch publication without touching a remote."""

    push_enabled = True

    def __init__(self) -> None:
        self.published: list[tuple[str, bool]] = []

    async def publish_run_branch(
        self,
        prepared: PreparedWorkspace,
        run: Any,
        *,
        expected_run_id: str | None = None,
        require_trailer: bool = False,
    ) -> None:
        assert expected_run_id == run.id
        self.published.append((prepared.branch, require_trailer))


class Jobs:
    """Absorb poller follow-up submissions."""

    async def submit(self, **kwargs: Any) -> None:
        del kwargs


def _job(kind: str) -> JobRunRecord:
    """Build one durable job for the finalize boundary."""
    return JobRunRecord(
        id=f"job-{kind}",
        kind=kind,
        ref_id=RUN_ID,
        status="running",
        progress=0.0,
        executor="local",
        external_job_id=None,
        attempt=1,
        payload={"runId": RUN_ID},
        result=None,
        error=None,
        created_by=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
        updated_at=NOW,
    )


def _gateway() -> FakeEvalGateway:
    """Deterministic gateway: baseline 80, candidate/final 85."""
    return FakeEvalGateway(
        EvalGatewayConfig.from_mapping(
            {
                "status": "completed",
                "currentScore": 80.0,
                "candidateScore": 85.0,
                "primaryMetricKey": "resolved_rate",
            },
        ),
    )


async def test_ensure_run_evaluation_is_idempotent(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """The unique run/kind pair returns the same pending row on retries."""
    _database, repository = state

    first = await repository.ensure_run_evaluation(RUN_ID, "validation_baseline")
    second = await repository.ensure_run_evaluation(RUN_ID, "validation_baseline")

    assert first.id == second.id
    assert first.eval_status == "pending"


async def test_baselines_and_test_final_feed_the_terminal_row(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """Both baselines and the held-out final persist before the final verdict."""
    _database, repository = state
    clock = NOW

    def now() -> datetime:
        return clock

    gateway = _gateway()
    submitter = EvolutionEvalSubmitter(
        repository,
        lambda _run: gateway,
        events=None,
        now=now,
        poll_interval=timedelta(seconds=1),
    )
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: gateway,
        Jobs(),
        events=None,
        now=now,
        poll_interval=timedelta(seconds=1),
        timeout=timedelta(hours=2),
    )

    run = await repository.get_run(RUN_ID)
    assert run is not None
    await submitter.submit_baselines(run)
    validation = await repository.get_run_evaluation(RUN_ID, "validation_baseline")
    test_baseline = await repository.get_run_evaluation(RUN_ID, "test_baseline")
    assert validation is not None and validation.eval_external_id
    assert test_baseline is not None and test_baseline.eval_external_id
    assert validation.eval_external_id != test_baseline.eval_external_id

    clock = NOW + timedelta(seconds=5)
    assert await poller.run_once() >= 1
    validation = await repository.get_run_evaluation(RUN_ID, "validation_baseline")
    test_baseline = await repository.get_run_evaluation(RUN_ID, "test_baseline")
    assert validation is not None and validation.eval_status == "completed"
    assert validation.eval_score == 80.0
    assert test_baseline is not None and test_baseline.eval_score == 80.0

    submitted_final = await submitter.submit_test_final(run)
    assert submitted_final.eval_status == "evaluating"
    clock = NOW + timedelta(seconds=10)
    assert await poller.run_once() >= 1
    test_final = await repository.get_run_evaluation(RUN_ID, "test_final")
    assert test_final is not None and test_final.eval_status == "completed"
    assert test_final.eval_score == 85.0

    workspaces = WorkspaceDouble()
    finalize = EvolutionFinalizeService(
        repository,
        workspaces,  # type: ignore[arg-type]
        events=None,
        eval_submitter=submitter,
        now=now,
    )
    finished = await finalize.handle(_job("evolution_finalize"))

    assert finished["finalized"] is True
    final = await repository.get_final(RUN_ID)
    assert final is not None
    assert final.init_score == 80.0
    assert final.best_score == 85.0
    assert final.verdict is False
    assert final.metrics == [
        {
            "name": "resolved_rate",
            "init": 80.0,
            "best": 85.0,
            "delta": 5.0,
            "unit": "",
            "direction": "higher_is_better",
        },
    ]
    run = await repository.get_run(RUN_ID)
    assert run is not None and run.status == "completed"


async def test_failed_run_evaluation_can_be_reset_for_retry(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """A failed baseline is cleared without touching a completed one."""
    _database, repository = state
    evaluation = await repository.ensure_run_evaluation(RUN_ID, "test_baseline")
    await repository.mark_run_eval_submitted(
        evaluation.id,
        external_id="eval-retry-1",
        started_at=NOW,
        next_poll_at=NOW + timedelta(seconds=1),
    )
    await repository.mark_run_eval_failed(
        evaluation.id,
        status="failed",
        error="platform unavailable",
        finished_at=NOW,
    )

    reset = await repository.reset_run_eval_for_retry(evaluation.id)

    assert reset.eval_status == "pending"
    assert reset.eval_external_id is None
    assert reset.eval_error is None


@pytest.mark.parametrize(
    ("kind", "test_budget_hours", "expected_status"),
    [
        ("test_baseline", 6, "evaluating"),
        ("test_final", 6, "evaluating"),
        ("validation_baseline", 2, "timeout"),
        ("test_baseline", 2, "timeout"),
    ],
)
async def test_execution_budget_depends_on_the_evaluation_kind(
    state: tuple[Any, EvolutionRepository],
    kind: str,
    test_budget_hours: int,
    expected_status: str,
) -> None:
    """Test-set evaluations get the larger budget; candidates keep 2 hours."""
    _database, repository = state
    started_at = NOW - timedelta(hours=2, minutes=30)
    evaluation = await repository.ensure_run_evaluation(RUN_ID, kind)
    await repository.mark_run_eval_submitted(
        evaluation.id,
        external_id=f"fake:{RUN_ID}:{kind}:{'c' * 40}",
        started_at=started_at,
        next_poll_at=NOW - timedelta(seconds=1),
    )
    gateway = FakeEvalGateway(
        EvalGatewayConfig.from_mapping(
            {
                "status": "running",
                "startedAt": started_at.isoformat(),
            },
        ),
    )
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: gateway,
        Jobs(),
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(seconds=1),
        timeout=timedelta(hours=2),
        test_timeout=timedelta(hours=test_budget_hours),
    )

    assert await poller.run_once() == 1

    observed = await repository.get_run_evaluation(RUN_ID, kind)
    assert observed is not None
    assert observed.eval_status == expected_status, observed.eval_error
    if expected_status == "timeout":
        assert observed.eval_error == "evaluation timed out"
