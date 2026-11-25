"""Submit-side gateway configuration errors land in blocked(eval), not failed(step).

The frozen run snapshot (``mode=http`` without a usable ``baseUrl``) must fail
through the same ``RunBlocked(stage=eval)`` path as polling-side configuration
errors, so ``/retry`` stays reachable instead of stranding a terminal failed run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_rounds, probe_clusters
from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalGatewayConfigError,
    RunBlocked,
)
from app.service.evolution.eval_poller import EvolutionEvalSubmitter
from app.service.evolution.gateway_factory import build_eval_gateway_factory

SH = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 18, 10, 0, tzinfo=SH)
CANDIDATE_COMMIT = "c" * 40


@pytest_asyncio.fixture
async def submit_state(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRepository]]:
    """Migrated SQLite state with one published round awaiting its evaluation."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m12-03-submit-config-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    # Same as production: the POST /runs creation-time snapshot lands here,
    # mode=http with the baseUrl deliberately missing.
    await repository.create_run(
        {
            "id": "run-submit",
            "title": "submit config error",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {"mode": "ai-eval-platform"},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": str(tmp_path / "example.git"),
            "sub_dir": "skills/deep-research",
            "base_ref": "v2.0.0",
            "base_commit": "a" * 40,
            "branch_name": "evo/20261118-run-submit",
            "repo_path": str(tmp_path / "repos" / "run-submit"),
            "workspace_path": str(tmp_path / "workspaces" / "run-submit"),
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
                probe_cluster_id="cluster-submit",
                run_id="run-submit",
                seq=1,
                probe_cluster_description="submit config issue",
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
                id="round-submit",
                run_id="run-submit",
                probe_cluster_id="cluster-submit",
                seq=1,
                status="evaluating",
                candidate_ref="evo/20261118-run-submit/candidate/r1",
                candidate_commit=CANDIDATE_COMMIT,
                candidate_message="candidate",
                push_status="succeeded",
                eval_external_id=None,
                eval_status="pending",
                eval_attempts=0,
            ),
        )
    try:
        yield database, repository
    finally:
        await database.dispose()


async def test_submit_gateway_config_error_blocks_eval_not_failed_step(
    submit_state: tuple[Database, EvolutionRepository],
) -> None:
    """A http snapshot without baseUrl blocks the run at eval, retryable."""
    _database, repository = submit_state
    run = await repository.get_run("run-submit")
    round_ = await repository.get_round("round-submit")
    assert run is not None and round_ is not None
    factory = build_eval_gateway_factory(
        Settings(jwt_secret=SecretStr("m12-03-submit-config-secret")),
    )
    submitter = EvolutionEvalSubmitter(
        repository,
        lambda resolved: factory(EvalGatewayConfig.from_mapping(resolved.eval_config)),
        events=None,
        now=lambda: NOW,
        poll_interval=timedelta(minutes=5),
    )

    with pytest.raises(RunBlocked) as excinfo:
        await submitter.submit(run, round_)

    assert excinfo.value.stage == "eval"
    assert excinfo.value.error_stage == "eval"
    assert "baseUrl" in str(excinfo.value)
    blocked = await repository.get_run("run-submit")
    assert blocked is not None
    assert blocked.status == "blocked"
    assert blocked.blocked_stage == "eval"
    assert blocked.error_stage == "eval"
    failed = await repository.get_round("round-submit")
    assert failed is not None
    assert failed.eval_status == "failed"
    assert failed.eval_external_id is None
    assert "baseUrl" in (failed.eval_error or "")


def test_submit_gateway_config_error_is_the_declared_error_family() -> None:
    """The factory raises the declared config error family for a http snapshot."""
    factory = build_eval_gateway_factory(
        Settings(jwt_secret=SecretStr("m12-03-submit-config-secret")),
    )
    with pytest.raises(EvalGatewayConfigError, match="baseUrl"):
        factory(EvalGatewayConfig.from_mapping({"mode": "ai-eval-platform"}))
