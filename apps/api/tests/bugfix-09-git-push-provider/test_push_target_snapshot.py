"""Run snapshots persist the derived push target and eval reuses it."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_rounds, evolution_runs, probe_clusters
from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalRequest,
    EvalResult,
    EvalStatus,
    EvalSubmission,
)
from app.service.evolution.eval_poller import EvolutionEvalSubmitter
from app.service.evolution.git_candidate import _prepared_workspace

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
PUSH_URL = "https://github.com/me/superpowers.git"
UPSTREAM_URL = "https://github.com/obra/superpowers.git"


class CaptureGateway:
    """Record the submitted request while satisfying the gateway contract."""

    def __init__(self) -> None:
        self.requests: list[EvalRequest] = []
        self.config = EvalGatewayConfig.from_mapping({})

    async def submit(self, request: EvalRequest) -> EvalSubmission:
        self.requests.append(request)
        return EvalSubmission(
            eval_id=f"fake:{request.run_id}:{request.evolution_round_id}:{request.commit}",
        )

    async def get_status(self, eval_id: str) -> EvalStatus:
        return EvalStatus(status="running")

    async def get_result(self, eval_id: str) -> EvalResult:
        return EvalResult(
            current_score=0.0,
            candidate_score=0.0,
            external_verdict="reject",
        )


@pytest_asyncio.fixture
async def repository(
    tmp_path: Path,
) -> AsyncIterator[tuple[EvolutionRepository, Database]]:
    """Provide migrated SQLite state with one push-target run and round."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("push-target-test-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    store = EvolutionRepository(database)
    try:
        await _seed(store, database)
        yield store, database
    finally:
        await database.dispose()


async def _seed(repository: EvolutionRepository, database: Database) -> None:
    """Insert one run and round at the evaluation submission boundary."""
    for run_id, push_repo_url in (("run-fork", PUSH_URL), ("run-legacy", "")):
        suffix = run_id.removeprefix("run-")
        await repository.create_run(
            {
                "id": run_id,
                "title": run_id,
                "mode": "full",
                "engine_key": "full",
                "eval_config": {},
                "target_config_id": None,
                "target_type": "skill",
                "target_name": "superpowers",
                "target_version": "v6.4.1",
                "repo_url": UPSTREAM_URL,
                "push_repo_url": push_repo_url,
                "sub_dir": "skills/deep-research",
                "base_ref": "v6.4.1",
                "base_commit": "a" * 40,
                "branch_name": f"evo/20261121-{run_id}",
                "repo_path": f"/tmp/repos/{run_id}",
                "workspace_path": f"/tmp/workspaces/{run_id}",
                "status": "running",
                "progress_unit": 4,
                "stats": {},
                "created_by": None,
                "created_at": NOW,
            },
        )
        if push_repo_url:
            async with database.transaction() as session:
                await session.execute(
                    update(evolution_runs)
                    .where(evolution_runs.c.id == run_id)
                    .values(push_repo_url=push_repo_url),
                )
        async with database.transaction() as session:
            await session.execute(
                insert(probe_clusters).values(
                    probe_cluster_id=f"cluster-{suffix}",
                    run_id=run_id,
                    seq=1,
                    probe_cluster_description="candidate",
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
                    id=f"round-{suffix}",
                    run_id=run_id,
                    probe_cluster_id=f"cluster-{suffix}",
                    seq=1,
                    status="evaluating",
                    candidate_ref=f"evo/20261121-{run_id}/candidate/r1",
                    candidate_commit="b" * 40,
                    candidate_message="candidate",
                    push_status="succeeded",
                    eval_status="pending",
                    eval_attempts=0,
                ),
            )


async def test_run_snapshot_round_trips_the_derived_push_target(
    repository: tuple[EvolutionRepository, Database],
) -> None:
    """The provider-derived URL survives the migration and read boundary."""
    store, _database = repository
    run = await store.get_run("run-fork")
    legacy = await store.get_run("run-legacy")

    assert run is not None and run.push_repo_url == PUSH_URL
    assert legacy is not None and legacy.push_repo_url == ""


async def test_candidate_retry_reconstructs_the_run_push_target(
    repository: tuple[EvolutionRepository, Database],
) -> None:
    """A later candidate push reuses the snapshot instead of the upstream."""
    store, _database = repository
    run = await store.get_run("run-fork")
    assert run is not None

    prepared = _prepared_workspace(run)

    assert prepared.push_url == PUSH_URL


async def test_evaluation_submits_the_same_push_target_as_the_candidate(
    repository: tuple[EvolutionRepository, Database],
) -> None:
    """Eval reads from the fork, so a candidate commit exists there first."""
    store, _database = repository
    run = await store.get_run("run-fork")
    round_ = await store.get_round("round-fork")
    assert run is not None and round_ is not None
    gateway = CaptureGateway()
    submitter = EvolutionEvalSubmitter(
        store,
        lambda _run: gateway,
        events=None,
    )

    await submitter.submit(run, round_)

    assert [request.repo_url for request in gateway.requests] == [PUSH_URL]


async def test_historical_run_falls_back_to_repo_url_for_evaluation(
    repository: tuple[EvolutionRepository, Database],
) -> None:
    """A run prepared before the migration keeps evaluating the upstream."""
    store, _database = repository
    run = await store.get_run("run-legacy")
    round_ = await store.get_round("round-legacy")
    assert run is not None and round_ is not None
    gateway = CaptureGateway()
    submitter = EvolutionEvalSubmitter(
        store,
        lambda _run: gateway,
        events=None,
    )

    await submitter.submit(run, round_)

    assert [request.repo_url for request in gateway.requests] == [UPSTREAM_URL]


def test_push_target_field_is_not_part_of_the_write_contract() -> None:
    """Targets stay deployment-selected; the run carries the derived snapshot."""
    from app.service.evolution.targets import EvolutionTargetWrite

    fields = EvolutionTargetWrite.model_fields
    assert "repo_url" in fields
    assert all(field.alias != "pushRepoUrl" for field in fields.values())
    assert all(name != "push_repo_url" for name in fields)


async def test_run_writer_defaults_historical_rows_to_empty_push_target(
    repository: tuple[EvolutionRepository, Database],
) -> None:
    """The additive migration keeps old rows readable without a backfill."""
    store, _database = repository
    run = await store.get_run("run-legacy")
    assert run is not None
    assert run.push_repo_url == ""

    updated = await store.mark_prepared(
        "run-legacy",
        status="running",
        progress_unit=5,
        repo_path=None,
        base_ref="v6.4.1",
        base_commit="a" * 40,
        branch_name="evo/20261121-run-legacy",
        workspace_path=None,
        stats={},
        push_repo_url=PUSH_URL,
    )
    assert updated.push_repo_url == PUSH_URL

    refreshed = await store.get_run("run-legacy")
    assert refreshed is not None and refreshed.push_repo_url == PUSH_URL
