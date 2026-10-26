"""Evolution repository cursor, cluster, round, and final contracts."""

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import evolution_targets, probe_reports
from app.db.models.evolution import (
    ClusterWrite,
    EvolutionRoundRecord,
    ProbeClusterLinkRecord,
    probe_cluster_probes,
)
from app.db.models.users import users
from app.service.evolution.state import StageConflict

NOW = datetime(2026, 10, 27, 1, 2, 3, tzinfo=UTC)
RUN_ID = "run-m5-01"
TARGET_ID = "target-m5-01"
USER_ID = "user-m5-01"


@pytest_asyncio.fixture
async def evolution_repository(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRepository]]:
    """Provide a migrated SQLite database with parent rows for a run."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr("m5-01-repository-test-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    await _seed_parent_rows(database)
    try:
        yield database, EvolutionRepository(database)
    finally:
        await database.dispose()


async def _seed_parent_rows(database: Database) -> None:
    """Insert the required user, target, and probe foreign-key parents."""
    async with database.transaction() as session:
        await session.execute(
            insert(users).values(
                id=USER_ID,
                username="m5-owner",
                password_hash="not-used",  # noqa: S106
                display_name="M5 Owner",
                role="admin",
                is_active=True,
                must_change_password=False,
                created_at=NOW,
                updated_at=NOW,
                last_login_at=None,
                password_changed_at=None,
            ),
        )
        await session.execute(
            insert(evolution_targets).values(
                id=TARGET_ID,
                object_type="skill",
                object_name="deep-research",
                repo_url="https://example.invalid/agent-skills.git",
                sub_dir="skills/deep-research",
                default_ref="v2.0.0",
                enabled=True,
                created_by=USER_ID,
                created_at=NOW,
                updated_at=NOW,
            ),
        )
        for probe_id, attribute_type in (
            ("p-model-1", "model"),
            ("p-model-2", "model"),
            ("p-prompt-1", "prompt"),
            ("p-error-1", "error"),
        ):
            await session.execute(
                insert(probe_reports).values(
                    probe_id=probe_id,
                    session_id="session-m5-01",
                    probe_type="skill",
                    probe_object="deep-research",
                    object_version="v2.0.0",
                    attribute_type=attribute_type,
                    probe_description=f"{attribute_type} issue",
                    probe_analysis=f"{attribute_type} analysis",
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )


def _run_values(**overrides: Any) -> dict[str, Any]:
    """Return one complete run insert payload with deterministic snapshots."""
    values = {
        "id": RUN_ID,
        "title": "deep-research 自进化",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {"gateway": "mock"},
        "target_config_id": TARGET_ID,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/agent-skills.git",
        "sub_dir": "skills/deep-research",
        "window_from": date(2026, 8, 20),
        "window_to": date(2026, 9, 10),
        "models": ["glm-5.3"],
        "stats": {"sessions": 4},
        "created_by": USER_ID,
        "created_at": NOW,
    }
    values.update(overrides)
    return values


async def test_run_creation_and_conditional_cursor_updates(
    evolution_repository: tuple[Database, EvolutionRepository],
) -> None:
    """A run persists snapshots and advances only from the expected cursor."""
    _, repository = evolution_repository
    run = await repository.create_run(_run_values())

    assert run.progress_unit == 0
    assert run.status == "preparing"
    assert run.eval_config == {"gateway": "mock"}
    assert run.stats == {"sessions": 4}

    assert (
        await repository.advance_unit(
            RUN_ID,
            expected=0,
            target=1,
            cluster_count=2,
        )
    ).progress_unit == 1
    assert (
        await repository.advance_unit(
            RUN_ID,
            expected=1,
            target=2,
            cluster_count=2,
        )
    ).progress_unit == 2

    with pytest.raises(StageConflict) as stale:
        await repository.advance_unit(
            RUN_ID,
            expected=1,
            target=2,
            cluster_count=2,
        )
    assert stale.value.current == 2
    assert stale.value.target == 2
    assert stale.value.status_code == 409

    with pytest.raises(LookupError, match="evolution run not found"):
        await repository.advance_unit(
            "missing-run",
            expected=0,
            target=1,
            cluster_count=2,
        )


async def test_cluster_writes_preserve_order_links_and_impact(
    evolution_repository: tuple[Database, EvolutionRepository],
) -> None:
    """Clusters use supplied order, frozen impact, and ordered probe links."""
    database, repository = evolution_repository
    await repository.create_run(_run_values())

    clusters = (
        _cluster(
            "model",
            "model 类问题 · 第 1 组\uff08占位聚类\uff09",
            ("p-model-1", "p-model-2"),
            impact=6.0,
        ),
        _cluster(
            "error",
            "error 类问题 · 第 1 组\uff08占位聚类\uff09",
            ("p-error-1",),
            impact=9.0,
        ),
    )
    written = await repository.replace_clusters(RUN_ID, clusters)

    assert [cluster.seq for cluster in written] == [1, 2]
    assert [cluster.probe_cluster_type for cluster in written] == ["model", "error"]
    assert [cluster.impact for cluster in written] == [6.0, 9.0]
    assert await repository.list_clusters(RUN_ID) == written

    async with database.session() as session:
        links = (
            (
                await session.execute(
                    select(probe_cluster_probes).order_by(probe_cluster_probes.c.id),
                )
            )
            .mappings()
            .all()
        )
    assert [
        ProbeClusterLinkRecord(
            id=int(row["id"]),
            probe_cluster_id=row["probe_cluster_id"],
            probe_id=row["probe_id"],
        )
        for row in links
    ] == [
        ProbeClusterLinkRecord(1, written[0].probe_cluster_id, "p-model-1"),
        ProbeClusterLinkRecord(2, written[0].probe_cluster_id, "p-model-2"),
        ProbeClusterLinkRecord(3, written[1].probe_cluster_id, "p-error-1"),
    ]


async def test_cluster_replacement_rolls_back_on_unique_violation(
    evolution_repository: tuple[Database, EvolutionRepository],
) -> None:
    """A failed replacement leaves the previous cluster snapshot intact."""
    _, repository = evolution_repository
    await repository.create_run(_run_values())
    original = await repository.replace_clusters(
        RUN_ID,
        (_cluster("model", "original", ("p-model-1",), impact=5.0),),
    )

    with pytest.raises(IntegrityError):
        await repository.replace_clusters(
            RUN_ID,
            (
                _cluster(
                    "error",
                    "broken",
                    ("p-error-1", "p-error-1"),
                    impact=9.0,
                ),
            ),
        )

    assert await repository.list_clusters(RUN_ID) == original


async def test_rounds_and_final_are_stable_and_idempotent(
    evolution_repository: tuple[Database, EvolutionRepository],
) -> None:
    """Rounds retain execution order and a run has one replaceable final row."""
    _, repository = evolution_repository
    await repository.create_run(_run_values())
    clusters = await repository.replace_clusters(
        RUN_ID,
        (
            _cluster("model", "model cluster", ("p-model-1",), impact=5.0),
            _cluster("error", "error cluster", ("p-error-1",), impact=9.0),
        ),
    )
    await repository.insert_rounds(
        (
            _round("round-2", clusters[1].probe_cluster_id, 2),
            _round("round-1", clusters[0].probe_cluster_id, 1),
        ),
    )

    rounds = await repository.list_rounds(RUN_ID)
    assert [round_.seq for round_ in rounds] == [1, 2]
    assert all(isinstance(round_, EvolutionRoundRecord) for round_ in rounds)

    first = await repository.write_final(
        {
            "run_id": RUN_ID,
            "best_version": "v2.0.1",
            "verdict": True,
            "best_score": 88.9,
            "init_score": 84.3,
            "metrics": [{"name": "score", "value": 88.9}],
        },
    )
    second = await repository.write_final(
        {
            "run_id": RUN_ID,
            "best_version": "v2.0.2",
            "verdict": False,
            "best_score": 80.0,
            "init_score": 84.3,
            "metrics": [{"name": "score", "value": 80.0}],
        },
    )

    assert first.best_version == "v2.0.1"
    assert second.best_version == "v2.0.2"


def _cluster(
    attribute_type: str,
    description: str,
    probes: tuple[str, ...],
    *,
    impact: float,
) -> ClusterWrite:
    """Build one repository cluster write without importing later service DTOs."""
    return ClusterWrite(
        type=cast(Any, attribute_type),
        description=description,
        probes=probes,
        impact=impact,
    )


def _round(round_id: str, cluster_id: str, seq: int) -> Mapping[str, Any]:
    """Return the minimum durable round payload."""
    return {
        "id": round_id,
        "run_id": RUN_ID,
        "probe_cluster_id": cluster_id,
        "seq": seq,
        "status": "pending",
    }
