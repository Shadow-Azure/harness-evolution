"""Run-level evaluations: storage, polling, and the held-out test-set final."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
        self.result_messages: list[str] = []
        self.result_commits: list[str] = []

    async def ensure_result_commit(
        self,
        prepared: PreparedWorkspace,
        *,
        run_id: str,
        message: str,
    ) -> str:
        del prepared
        assert run_id == RUN_ID
        self.result_messages.append(message)
        commit = "c" * 40
        self.result_commits.append(commit)
        return commit

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


async def test_startup_submits_only_the_validation_baseline(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """The test set is never launched before the run reaches finalization."""
    _database, repository = state
    clock = NOW

    def now() -> datetime:
        return clock

    submitter = EvolutionEvalSubmitter(
        repository,
        lambda _run: _gateway(),
        events=None,
        now=now,
        poll_interval=timedelta(seconds=1),
    )

    run = await repository.get_run(RUN_ID)
    assert run is not None
    await submitter.submit_validation_baseline(run)

    validation = await repository.get_run_evaluation(RUN_ID, "validation_baseline")
    assert validation is not None and validation.eval_external_id
    assert await repository.get_run_evaluation(RUN_ID, "test_baseline") is None
    assert await repository.get_run_evaluation(RUN_ID, "test_final") is None


async def test_finalize_submits_both_test_evaluations_for_the_terminal_row(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """The finalize stage launches baseline and final, waits for both, then writes."""
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
    workspaces = WorkspaceDouble()
    finalize = EvolutionFinalizeService(
        repository,
        workspaces,  # type: ignore[arg-type]
        events=None,
        eval_submitter=submitter,
        now=now,
    )

    run = await repository.get_run(RUN_ID)
    assert run is not None
    await submitter.submit_validation_baseline(run)
    clock = NOW + timedelta(seconds=5)
    assert await poller.run_once() >= 1
    validation = await repository.get_run_evaluation(RUN_ID, "validation_baseline")
    assert validation is not None and validation.eval_status == "completed"

    pending = await finalize.handle(_job("evolution_finalize"))
    assert pending["finalized"] is False
    assert pending["reason"] == "test-set evaluations are pending"
    test_baseline = await repository.get_run_evaluation(RUN_ID, "test_baseline")
    test_final = await repository.get_run_evaluation(RUN_ID, "test_final")
    assert test_baseline is not None and test_baseline.eval_external_id
    assert test_final is not None and test_final.eval_external_id
    assert test_baseline.eval_external_id != test_final.eval_external_id
    persisted = await repository.get_run(RUN_ID)
    assert persisted is not None and persisted.result_commit == "c" * 40
    assert await repository.get_final(RUN_ID) is None
    assert len(workspaces.result_commits) == 1
    assert "Harness-Run-Id: run-evaluations" in workspaces.result_messages[0]
    assert "Harness-Verdict: no-acceptance " in workspaces.result_messages[0]

    # A retry before polling reuses the persisted result commit.
    replay = await finalize.handle(_job("evolution_finalize"))
    assert replay["finalized"] is False
    assert len(workspaces.result_commits) == 1

    clock = NOW + timedelta(seconds=10)
    assert await poller.run_once() >= 2
    test_baseline = await repository.get_run_evaluation(RUN_ID, "test_baseline")
    test_final = await repository.get_run_evaluation(RUN_ID, "test_final")
    assert test_baseline is not None and test_baseline.eval_score == 80.0
    assert test_final is not None and test_final.eval_score == 85.0

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
    assert workspaces.published == [("evo/20261125-run-evaluations", True)]


async def test_finalize_waits_for_both_test_evaluations(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """A completed baseline alone must not write the final row."""
    _database, repository = state
    clock = NOW

    def now() -> datetime:
        return clock

    submitter = EvolutionEvalSubmitter(
        repository,
        lambda _run: _gateway(),
        events=None,
        now=now,
        poll_interval=timedelta(seconds=1),
    )
    workspaces = WorkspaceDouble()
    finalize = EvolutionFinalizeService(
        repository,
        workspaces,  # type: ignore[arg-type]
        events=None,
        eval_submitter=submitter,
        now=now,
    )

    run = await repository.get_run(RUN_ID)
    assert run is not None
    await finalize.handle(_job("evolution_finalize"))
    baseline = await repository.get_run_evaluation(RUN_ID, "test_baseline")
    final = await repository.get_run_evaluation(RUN_ID, "test_final")
    assert baseline is not None and final is not None
    completed = await repository.save_run_eval_result(
        baseline.id,
        result={
            "candidateScore": 80.0,
            "primaryMetricKey": "resolved_rate",
            "direction": "higher_is_better",
            "metrics": [],
        },
        score=80.0,
        finished_at=NOW,
    )
    assert completed is True

    pending = await finalize.handle(_job("evolution_finalize"))
    assert pending["finalized"] is False
    assert await repository.get_final(RUN_ID) is None


async def test_legacy_completed_test_final_is_reused_without_a_result_commit(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """An already completed legacy test final is never replaced by a result commit."""
    _database, repository = state

    async def finish(kind: str, score: float) -> None:
        row = await repository.ensure_run_evaluation(RUN_ID, kind)
        if row.eval_external_id is None:
            await repository.mark_run_eval_submitted(
                row.id,
                external_id=f"legacy-{kind}",
                started_at=NOW,
                next_poll_at=NOW + timedelta(seconds=1),
            )
        assert await repository.save_run_eval_result(
            row.id,
            result={
                "candidateScore": score,
                "primaryMetricKey": "resolved_rate",
                "direction": "higher_is_better",
                "metrics": [],
            },
            score=score,
            finished_at=NOW,
        )

    await finish("test_baseline", 80.0)
    await finish("test_final", 85.0)
    workspaces = WorkspaceDouble()
    finalize = EvolutionFinalizeService(
        repository,
        workspaces,  # type: ignore[arg-type]
        events=None,
        eval_submitter=EvolutionEvalSubmitter(
            repository,
            lambda _run: _gateway(),
            events=None,
            now=lambda: NOW,
            poll_interval=timedelta(seconds=1),
        ),
        now=lambda: NOW,
    )

    result = await finalize.handle(_job("evolution_finalize"))

    assert result["finalized"] is True
    assert workspaces.result_commits == []
    run = await repository.get_run(RUN_ID)
    assert run is not None and run.result_commit is None
    final = await repository.get_final(RUN_ID)
    assert final is not None
    assert final.init_score == 80.0
    assert final.best_score == 85.0


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


async def test_failed_test_evaluations_resubmit_to_their_original_targets(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """Retry re-targets the baseline and the result commit without re-running rounds."""
    _database, repository = state
    await repository.record_result_commit(RUN_ID, "c" * 40)
    submitter = EvolutionEvalSubmitter(
        repository,
        lambda _run: _gateway(),
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(seconds=1),
    )

    baseline = await repository.ensure_run_evaluation(RUN_ID, "test_baseline")
    await repository.mark_run_eval_submitted(
        baseline.id,
        external_id="eval-baseline-failed",
        started_at=NOW,
        next_poll_at=NOW + timedelta(seconds=1),
    )
    await repository.mark_run_eval_failed(
        baseline.id,
        status="failed",
        error="platform unavailable",
        finished_at=NOW,
    )
    await repository.reset_run_eval_for_retry(baseline.id)

    final = await repository.ensure_run_evaluation(RUN_ID, "test_final")
    await repository.mark_run_eval_submitted(
        final.id,
        external_id="eval-final-failed",
        started_at=NOW,
        next_poll_at=NOW + timedelta(seconds=1),
    )
    await repository.mark_run_eval_failed(
        final.id,
        status="timeout",
        error="platform timed out",
        finished_at=NOW,
    )
    await repository.reset_run_eval_for_retry(final.id)

    run = await repository.get_run(RUN_ID)
    assert run is not None
    resubmitted_baseline = await submitter.resubmit_run_evaluation(run, "test_baseline")
    resubmitted_final = await submitter.resubmit_run_evaluation(run, "test_final")
    assert resubmitted_baseline.eval_external_id == f"fake:{RUN_ID}:test_baseline:{'a' * 40}"
    assert resubmitted_final.eval_external_id == f"fake:{RUN_ID}:test_final:{'c' * 40}"
