"""Transient polling failures defer the next poll instead of failing the eval.

A poll request is an observation, not a verdict: gateway errors marked
``retryable`` (network timeouts, connection failures, HTTP 429/5xx) only push
``next_poll_at`` forward under the existing 2h timeout cap; non-retryable
errors keep the existing blocked(stage=eval) semantics.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_rounds, probe_clusters
from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalMeasurement,
    EvalStatus,
)
from app.service.evolution.eval_poller import EvolutionEvalPoller
from app.third_party_api.eval_gateway.base import EvalGatewayError

SH = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=SH)
EXTERNAL_ID = "eval-transient-1"


class _RetryableGateway:
    """Gateway seam whose status request fails with a retryable transport error."""

    config = EvalGatewayConfig.from_mapping({"mode": "http"})

    def __init__(self, *, retryable: bool, fail_status: bool = True) -> None:
        self._retryable = retryable
        self._fail_status = fail_status

    async def get_status(self, eval_id: str) -> EvalStatus:
        del eval_id
        if self._fail_status:
            raise EvalGatewayError(
                "evaluation platform status request failed",
                retryable=self._retryable,
            )
        return EvalStatus(status="completed")

    async def get_result(self, eval_id: str) -> EvalMeasurement:
        del eval_id
        if self._fail_status:
            raise AssertionError("a deferred round must not request its result yet")
        return EvalMeasurement(
            candidate_score=85.0,
            primary_metric_key="resolved_rate",
            direction="higher_is_better",
        )


class _HealedGateway:
    """Healthy gateway seam used to prove a deferred round really recovers."""

    config = EvalGatewayConfig.from_mapping({"mode": "http"})

    async def get_status(self, eval_id: str) -> EvalStatus:
        del eval_id
        return EvalStatus(status="completed")

    async def get_result(self, eval_id: str) -> EvalMeasurement:
        del eval_id
        return EvalMeasurement(
            candidate_score=85.0,
            primary_metric_key="resolved_rate",
            direction="higher_is_better",
        )


@pytest_asyncio.fixture
async def poll_state(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRepository]]:
    """Migrated SQLite state with one evaluating round that is due for polling."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m12-03-transient-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    await repository.create_run(
        {
            "id": "run-transient",
            "title": "transient poll",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {"mode": "http"},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": str(tmp_path / "example.git"),
            "sub_dir": "skills/deep-research",
            "base_ref": "v2.0.0",
            "base_commit": "a" * 40,
            "branch_name": "evo/20261118-run-transient",
            "repo_path": str(tmp_path / "repos" / "run-transient"),
            "workspace_path": str(tmp_path / "workspaces" / "run-transient"),
            "status": "running",
            "progress_unit": 5,
            "stats": {},
            "created_by": None,
            "created_at": NOW,
        },
    )
    async with database.transaction() as session:
        await session.execute(
            insert(probe_clusters).values(
                probe_cluster_id="cluster-transient",
                run_id="run-transient",
                seq=1,
                probe_cluster_description="transient issue",
                probe_cluster_type="error",
                confidence=0.9,
                impact=0.8,
                severity=0.8,
                rank=1,
                created_at=NOW,
            ),
        )
        await session.execute(
            insert(evolution_rounds).values(
                id="round-transient",
                run_id="run-transient",
                probe_cluster_id="cluster-transient",
                seq=1,
                status="evaluating",
                candidate_ref="evo/20261118-run-transient/candidate/r1",
                candidate_commit="b" * 40,
                candidate_message="candidate",
                push_status="succeeded",
                eval_external_id=EXTERNAL_ID,
                eval_status="evaluating",
                eval_attempts=1,
                eval_next_poll_at=NOW - timedelta(seconds=1),
                eval_started_at=NOW - timedelta(minutes=1),
            ),
        )
    try:
        yield database, repository
    finally:
        await database.dispose()


def _poller(
    repository: EvolutionRepository,
    gateway: Any,
    **overrides: Any,
) -> EvolutionEvalPoller:
    """Build one poller around a fixed gateway with a pinned clock."""
    values: dict[str, Any] = {
        "events": None,
        "now": lambda: NOW,
        "poll_interval": timedelta(minutes=5),
        "timeout": timedelta(hours=2),
    }
    values.update(overrides)
    return EvolutionEvalPoller(
        repository,
        lambda _run: gateway,
        _NoJobs(),
        **values,
    )


async def test_retryable_poll_error_defers_next_poll_and_recovers(
    poll_state: tuple[Database, EvolutionRepository],
) -> None:
    """A retryable status failure pushes next_poll_at; a healed poll completes."""
    _database, repository = poll_state
    gateway = _RetryableGateway(retryable=True)
    poller = _poller(repository, gateway)

    assert await poller.run_once() == 1
    run = await repository.get_run("run-transient")
    round_ = await repository.get_round("round-transient")
    assert run is not None and round_ is not None
    assert run.status == "running"
    assert round_.status == "evaluating"
    assert round_.eval_status == "evaluating"
    assert round_.eval_external_id == EXTERNAL_ID
    assert round_.eval_next_poll_at == NOW + timedelta(minutes=5)
    assert round_.eval_error is None

    gateway._retryable = True
    gateway._fail_status = False
    healed = _poller(repository, gateway, now=lambda: NOW + timedelta(minutes=6))
    assert await healed.run_once() == 1
    recovered = await repository.get_round("round-transient")
    assert recovered is not None
    assert recovered.eval_status == "completed"


async def test_non_retryable_poll_error_still_blocks_eval(
    poll_state: tuple[Database, EvolutionRepository],
) -> None:
    """A final gateway error keeps the existing blocked(stage=eval) semantics."""
    _database, repository = poll_state
    gateway = _RetryableGateway(retryable=False)
    poller = _poller(repository, gateway)

    assert await poller.run_once() == 1

    run = await repository.get_run("run-transient")
    round_ = await repository.get_round("round-transient")
    assert run is not None and round_ is not None
    assert run.status == "blocked"
    assert run.blocked_stage == "eval"
    assert round_.eval_status == "failed"
    assert round_.eval_next_poll_at is None


async def test_retryable_poll_errors_never_outlive_the_eval_timeout(
    poll_state: tuple[Database, EvolutionRepository],
) -> None:
    """The 2h timeout caps retryable deferrals and declares the round timed out."""
    database, repository = poll_state
    async with database.transaction() as session:
        await session.execute(
            update(evolution_rounds)
            .where(evolution_rounds.c.id == "round-transient")
            .values(eval_started_at=NOW - timedelta(hours=3)),
        )
    gateway = _RetryableGateway(retryable=True)
    poller = _poller(repository, gateway)

    assert await poller.run_once() == 1

    run = await repository.get_run("run-transient")
    round_ = await repository.get_round("round-transient")
    assert run is not None and round_ is not None
    assert run.status == "blocked"
    assert run.blocked_stage == "eval"
    assert round_.eval_status == "timeout"


async def test_retryable_deferral_keeps_the_due_timer_durable(
    poll_state: tuple[Database, EvolutionRepository],
) -> None:
    """A deferred round is not due again until its pushed next_poll_at arrives."""
    _database, repository = poll_state
    gateway = _RetryableGateway(retryable=True)
    poller = _poller(repository, gateway, poll_interval=timedelta(minutes=5))
    assert await poller.run_once() == 1
    deferred = await repository.get_round("round-transient")
    assert deferred is not None
    assert deferred.eval_next_poll_at == NOW + timedelta(minutes=5)

    rested = _poller(repository, gateway, now=lambda: NOW + timedelta(seconds=30))
    assert await rested.run_once() == 0

    healed = _poller(repository, _HealedGateway(), now=lambda: NOW + timedelta(minutes=6))
    assert await healed.run_once() == 1
    run = await repository.get_run("run-transient")
    assert run is not None and run.status == "running"


class _NoJobs:
    """Job seam that absorbs follow-up submissions without scheduling."""

    async def submit(self, **kwargs: Any) -> None:
        """Absorb one follow-up submission."""
        del kwargs
