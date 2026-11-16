"""Attribution cache upsert, reuse, and multi-link repository contracts."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.attributions import (
    AttributionRepository,
    ProbeWrite,
    attribution_cache_key,
)
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_case_analysis, bad_cases, probe_reports
from app.db.models.evolution import evolution_runs
from app.utils.time import SHANGHAI, as_shanghai

NOW = datetime(2026, 11, 17, 9, tzinfo=SHANGHAI)
LATER = datetime(2026, 11, 17, 10, tzinfo=SHANGHAI)
SESSION_ID = "94000000-0000-4000-8000-000000000001"
CASE_ID = "bc-attribution-a"
OTHER_CASE_ID = "bc-attribution-b"
RUN_ID = "run-attribution-a"
OTHER_RUN_ID = "run-attribution-b"


@pytest_asyncio.fixture
async def attribution_repository(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, AttributionRepository]]:
    """Provide a migrated SQLite database with two bad cases."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'attribution-repository.db'}",
        ),
    )
    await database.start()
    await upgrade_database(database)
    async with database.transaction() as session:
        for run_id in (RUN_ID, OTHER_RUN_ID):
            await session.execute(
                evolution_runs.insert().values(
                    id=run_id,
                    title=run_id,
                    mode="full",
                    engine_key="full",
                    eval_config={},
                    target_type="skill",
                    target_name="deep-research",
                    target_version="v2.0.0",
                    repo_url="https://example.invalid/skills.git",
                    sub_dir="skills/deep-research",
                    status="running",
                    created_at=NOW,
                ),
            )
        for case_id in (CASE_ID, OTHER_CASE_ID):
            await session.execute(
                bad_cases.insert().values(
                    bad_case_id=case_id,
                    bad_case_session_id=SESSION_ID,
                    bad_case_type="self",
                    object_name="deep-research",
                    object_type="skill",
                    object_version="v2.0.0",
                    bad_case_agent_id=None,
                    title=case_id,
                    bad_case_description="reason",
                    meta_data=None,
                    source="fixtures",
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
    try:
        yield database, AttributionRepository(database)
    finally:
        await database.dispose()


def probe_write(
    probe_id: str = "probe-a",
    *,
    bad_case_id: str = CASE_ID,
    probe_object: str = "deep-research",
    version: str | None = "v2.0.0",
    policy_version: str = "v1",
    engine: str = "engine-a",
    conclusion: str = "attributed",
    attribute_type: str | None = "prompt",
    description: str = "description",
    confidence: float = 0.8,
    created_run_id: str | None = RUN_ID,
    updated_at: datetime = NOW,
) -> ProbeWrite:
    """Build one V2 probe write with deterministic defaults."""
    return ProbeWrite(
        probe_id=probe_id,
        workspace_id="ws-default",
        session_id=SESSION_ID,
        bad_case_id=bad_case_id,
        probe_type="skill",
        probe_object=probe_object,
        object_version=version,
        attribute_type=attribute_type,
        conclusion=conclusion,
        confidence=confidence,
        probe_description=description,
        probe_analysis="analysis",
        policy_version=policy_version,
        attribution_engine=engine,
        created_run_id=created_run_id,
        created_at=NOW,
        updated_at=updated_at,
    )


async def test_same_case_links_multiple_attributions(
    attribution_repository: tuple[Database, AttributionRepository],
) -> None:
    """One case keeps several probes with distinct object versions."""
    _database, repository = attribution_repository
    assert await repository.upsert_probe(probe_write("probe-a", version="v2.0.0")) == "probe-a"
    assert (
        await repository.upsert_probe(
            probe_write("probe-b", version="v1.0.0", updated_at=LATER),
        )
        == "probe-b"
    )
    await repository.upsert_link(CASE_ID, "probe-a", NOW)
    await repository.upsert_link(CASE_ID, "probe-b", NOW)

    records = await repository.list_attributions(CASE_ID)
    assert [record.probe_id for record in records] == ["probe-b", "probe-a"]
    assert records[0].analysis_status is None
    assert records[0].analysis_result is None
    assert records[0].cache_key == attribution_cache_key(
        "ws-default",
        CASE_ID,
        "skill",
        "deep-research",
        "v1.0.0",
        "v1",
        "engine-a",
    )
    assert await repository.attribution_count(CASE_ID) == 2
    assert (await repository.get_attribution(CASE_ID, "probe-a")) is not None
    assert (await repository.get_attribution(OTHER_CASE_ID, "probe-a")) is None
    assert [record.probe_id for record in await repository.list_attributions(CASE_ID, 1, 1)] == [
        "probe-a",
    ]


async def test_repeated_upsert_link_stays_one_row(
    attribution_repository: tuple[Database, AttributionRepository],
) -> None:
    """The (case, probe) unique rule makes link writes idempotent."""
    database, repository = attribution_repository
    await repository.upsert_probe(probe_write("probe-a"))
    await repository.upsert_link(CASE_ID, "probe-a", NOW)
    await repository.upsert_link(CASE_ID, "probe-a", LATER)

    async with database.session() as session:
        links = int(
            (
                await session.execute(
                    select(func.count()).select_from(bad_case_analysis),
                )
            ).scalar_one(),
        )
    assert links == 1
    assert await repository.attribution_count(CASE_ID) == 1
    record = await repository.get_attribution(CASE_ID, "probe-a")
    assert record is not None
    assert record.updated_at == as_shanghai(NOW)
    async with database.session() as session:
        link_updated_at: datetime = (
            await session.execute(select(bad_case_analysis.c.updated_at))
        ).scalar_one()
    assert link_updated_at == LATER.replace(tzinfo=None)


async def test_cache_upsert_reuses_the_existing_probe_id(
    attribution_repository: tuple[Database, AttributionRepository],
) -> None:
    """A second write with the same seven-part cache key updates in place."""
    database, repository = attribution_repository
    first = probe_write("probe-first")
    assert await repository.upsert_probe(first) == "probe-first"

    second = replace(
        first,
        probe_id="probe-second",
        conclusion="non_target",
        attribute_type=None,
        probe_description="updated description",
        confidence=0.5,
        created_run_id=OTHER_RUN_ID,
        updated_at=LATER,
    )
    assert await repository.upsert_probe(second) == "probe-first"

    async with database.session() as session:
        rows = (await session.execute(select(probe_reports))).mappings().all()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["probe_id"] == "probe-first"
    assert row["probe_description"] == "updated description"
    assert row["conclusion"] == "non_target"
    assert row["attribute_type"] is None
    assert row["confidence"] == pytest.approx(0.5)
    assert row["created_run_id"] == OTHER_RUN_ID
    assert row["created_at"] == NOW.replace(tzinfo=None)
    assert row["cache_key"] == second.cache_key


async def test_concurrent_cache_upserts_converge_on_one_probe(
    attribution_repository: tuple[Database, AttributionRepository],
) -> None:
    """Concurrent writers of the same cache key never create duplicate rows."""
    database, repository = attribution_repository
    base = probe_write("probe-seed")
    probe_ids = await asyncio.gather(
        *(
            repository.upsert_probe(
                replace(base, probe_id=f"probe-race-{index}", probe_description=f"writer {index}"),
            )
            for index in range(4)
        ),
    )

    assert len(set(probe_ids)) == 1
    async with database.session() as session:
        count = int(
            (await session.execute(select(func.count()).select_from(probe_reports))).scalar_one(),
        )
    assert count == 1


async def test_reuse_is_idempotent_per_run_and_tracks_last_run(
    attribution_repository: tuple[Database, AttributionRepository],
) -> None:
    """A repeated hit from the same run is not counted twice."""
    database, repository = attribution_repository
    await repository.upsert_probe(probe_write("probe-a"))
    assert await repository.reuse("probe-a", RUN_ID, NOW) == 1
    assert await repository.reuse("probe-a", RUN_ID, LATER) == 0
    assert await repository.reuse("probe-a", OTHER_RUN_ID, LATER) == 1
    assert await repository.reuse("probe-missing", OTHER_RUN_ID, LATER) == 0

    async with database.session() as session:
        row = (await session.execute(select(probe_reports))).mappings().one()
    assert row["reused_count"] == 2
    assert row["last_reused_run_id"] == OTHER_RUN_ID
    assert row["updated_at"] == LATER.replace(tzinfo=None)


async def test_probe_write_validates_identity_and_normalizes_version(
    attribution_repository: tuple[Database, AttributionRepository],
) -> None:
    """Malformed V2 identities fail before SQL instead of degrading at runtime."""
    _database, _repository = attribution_repository
    base = probe_write()
    with pytest.raises(ValueError, match="probe_id"):
        replace(base, probe_id="")
    with pytest.raises(ValueError, match="workspace_id"):
        replace(base, workspace_id="")
    with pytest.raises(ValueError, match="bad_case_id"):
        replace(base, bad_case_id="")
    with pytest.raises(ValueError, match="session_id"):
        replace(base, session_id="")
    with pytest.raises(ValueError, match="probe_type"):
        replace(base, probe_type="workflow")
    with pytest.raises(ValueError, match="conclusion"):
        replace(base, conclusion="maybe")
    with pytest.raises(ValueError, match="confidence"):
        replace(base, confidence=1.5)
    with pytest.raises(ValueError, match="confidence"):
        replace(base, confidence=-0.1)

    blank = replace(base, object_version="")
    missing = replace(base, object_version=None)
    assert blank.object_version is None
    assert blank.cache_key == missing.cache_key


def test_probe_write_accepts_knowledge_for_m10_03() -> None:
    """The m10-03 knowledge attribution writer can use the same cache identity."""
    knowledge = replace(probe_write(), probe_type="knowledge")

    assert knowledge.probe_type == "knowledge"
    assert knowledge.cache_key != probe_write().cache_key


async def test_attribution_count_distincts_the_object_identity(
    attribution_repository: tuple[Database, AttributionRepository],
) -> None:
    """Two probes of the same object and version count once."""
    _database, repository = attribution_repository
    await repository.upsert_probe(probe_write("probe-policy-v1", policy_version="v1"))
    await repository.upsert_probe(probe_write("probe-policy-v2", policy_version="v2"))
    await repository.upsert_link(CASE_ID, "probe-policy-v1", NOW)
    await repository.upsert_link(CASE_ID, "probe-policy-v2", NOW)

    assert await repository.attribution_count(CASE_ID) == 1
    assert len(await repository.list_attributions(CASE_ID)) == 2
