"""Transport retries reuse the idempotency key; terminal failures get a new one."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_rounds, probe_clusters
from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalRequest,
    EvalSubmission,
    RunBlocked,
)
from app.service.evolution.eval_poller import EvolutionEvalSubmitter
from app.third_party_api.eval_gateway.base import EvalGatewayError

SH = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 25, 10, 0, tzinfo=SH)
RUN_ID = "run-attempts"
ROUND_ID = "round-attempts"


@pytest_asyncio.fixture
async def state(tmp_path: Path) -> AsyncIterator[tuple[Any, EvolutionRepository]]:
    """Provide one running run with a pushed, evaluating candidate round."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("bugfix-63-attempts-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    await repository.create_run(
        {
            "id": RUN_ID,
            "title": "attempt keys",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {
                "mode": "fake",
                "primaryMetricKey": "resolved_rate",
            },
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": "https://example.invalid/repo.git",
            "sub_dir": "skills/deep-research",
            "base_ref": "v2.0.0",
            "base_commit": "a" * 40,
            "branch_name": "evo/20261125-run-attempts",
            "repo_path": str(tmp_path / "repo"),
            "workspace_path": str(tmp_path / "workspace"),
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
                probe_cluster_id="cluster-attempts",
                run_id=RUN_ID,
                seq=1,
                probe_cluster_description="attempt keys",
                probe_cluster_type="error",
                created_at=NOW,
            ),
        )
        await session.execute(
            insert(evolution_rounds).values(
                id=ROUND_ID,
                run_id=RUN_ID,
                probe_cluster_id="cluster-attempts",
                seq=1,
                status="evaluating",
                candidate_ref="evo/20261125-run-attempts/candidate/r1",
                candidate_commit="b" * 40,
                candidate_message="candidate",
                push_status="succeeded",
                eval_status="pending",
            ),
        )
    try:
        yield database, repository
    finally:
        await database.dispose()


class RecordingGateway:
    """Gateway whose first submit loses the acknowledgment but creates a run."""

    config = EvalGatewayConfig.from_mapping({})

    def __init__(self, *, lose_first_ack: bool = True) -> None:
        self.requests: list[EvalRequest] = []
        self._lose_first_ack = lose_first_ack

    async def submit(self, request: EvalRequest) -> EvalSubmission:
        self.requests.append(request)
        if self._lose_first_ack and len(self.requests) == 1:
            raise EvalGatewayError("lost 202", retryable=True)
        return EvalSubmission(eval_id=f"eval-{len(self.requests)}")


async def test_lost_ack_retry_reuses_the_same_idempotency_key(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """A missing 202 must not consume an attempt or create a second platform run."""
    _database, repository = state
    gateway = RecordingGateway()
    submitter = EvolutionEvalSubmitter(
        repository,
        lambda _run: gateway,  # type: ignore[arg-type,return-value]
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(seconds=1),
    )
    run = await repository.get_run(RUN_ID)
    round_ = await repository.get_round(ROUND_ID)
    assert run is not None and round_ is not None

    with pytest.raises(RunBlocked):
        await submitter.submit(run, round_)

    failed = await repository.get_round(ROUND_ID)
    assert failed is not None and failed.eval_status == "failed"
    reset = await repository.reset_round_for_eval_retry(RUN_ID, ROUND_ID)
    submitted = await submitter.submit(run, reset)

    assert submitted.eval_external_id == "eval-2"
    assert len(gateway.requests) == 2
    assert gateway.requests[0].idempotency_key == gateway.requests[1].idempotency_key
    assert gateway.requests[1].attempt == 1


async def test_confirmed_terminal_failure_gets_a_new_key(
    state: tuple[Any, EvolutionRepository],
) -> None:
    """Once the platform accepted the run and later failed it, a retry is a new attempt."""
    _database, repository = state
    gateway = RecordingGateway(lose_first_ack=False)
    submitter = EvolutionEvalSubmitter(
        repository,
        lambda _run: gateway,  # type: ignore[arg-type,return-value]
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(seconds=1),
    )
    run = await repository.get_run(RUN_ID)
    round_ = await repository.get_round(ROUND_ID)
    assert run is not None and round_ is not None

    submitted = await submitter.submit(run, round_)
    assert submitted.eval_attempts == 1
    await repository.mark_eval_failed(
        run.id,
        submitted.id,
        status="failed",
        error="platform reported failure",
        finished_at=NOW,
    )
    reset = await repository.reset_round_for_eval_retry(run.id, submitted.id)
    retried = await submitter.submit(run, reset)

    assert retried.eval_attempts == 2
    assert len(gateway.requests) == 2
    assert gateway.requests[0].idempotency_key != gateway.requests[1].idempotency_key
    assert gateway.requests[1].attempt == 2
