"""Repository reads backing the six-step stage payloads."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.probe_query import ProbeQueryRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_case_analysis, bad_cases, probe_reports
from app.db.models.evolution import (
    evolution_finals,
    probe_cluster_probes,
    probe_clusters,
)
from tests.six_step_seed import (
    NOW,
    RUN_ID,
    SESSION_ID,
    seed_external_corpus,
    seed_run,
)

SECRET = "m5-06-repository-signing-secret"


@pytest_asyncio.fixture
async def step_database(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRepository, ProbeQueryRepository]]:
    """Provide a migrated SQLite database with both repositories bound."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            jwt_secret=SecretStr(SECRET),
        ),
    )
    await database.start()
    await upgrade_database(database)
    try:
        yield database, EvolutionRepository(database), ProbeQueryRepository(database)
    finally:
        await database.dispose()


async def _seed_clustered_run(
    database: Database,
    repository: EvolutionRepository,
    *,
    with_final: bool = False,
) -> None:
    """Insert one run with two clusters, ordered links, and an optional final."""
    await seed_external_corpus(database)
    await seed_run(database, progress_unit=4)
    async with database.transaction() as session:
        await session.execute(
            insert(bad_cases),
            [
                {
                    "bad_case_id": "bc-050b-04",
                    "bad_case_session_id": SESSION_ID,
                    "bad_case_type": "discovery",
                    "object_name": "general-purpose",
                    "object_type": "agent",
                    "object_version": None,
                    "bad_case_agent_id": None,
                    "title": "工具层检索结果未去重",
                    "bad_case_description": "subagent发现前置步骤存在问题：工具层检索结果未去重",  # noqa: RUF001
                    "meta_data": {},
                    "source": "fixtures",
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            ],
        )
        await session.execute(
            insert(probe_reports),
            [
                {
                    "probe_id": "pr-050b-04",
                    "session_id": SESSION_ID,
                    "probe_type": "agent",
                    "probe_object": "deep-research",
                    "object_version": "v2.0.0",
                    "attribute_type": "prompt",
                    "probe_description": "检索结果未去重",
                    "probe_analysis": "未约定去重步骤",
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            ],
        )
        await session.execute(
            insert(bad_case_analysis),
            [
                {
                    "bad_case_id": "bc-050b-04",
                    "analysis_status": "analyzed_issue",
                    "probe_id": "pr-050b-04",
                    "analysis_result": {"summary": "工具层检索未去重"},
                    "updated_at": NOW,
                },
            ],
        )
        await session.execute(
            insert(probe_clusters),
            [
                {
                    "probe_cluster_id": "C2",
                    "run_id": RUN_ID,
                    "seq": 2,
                    "probe_cluster_description": "检索结果未去重",
                    "probe_cluster_type": "prompt",
                    "confidence": 0.6,
                    "impact": 7,
                    "severity": 4.2,
                    "rank": 2,
                    "created_at": NOW,
                },
                {
                    "probe_cluster_id": "C1",
                    "run_id": RUN_ID,
                    "seq": 1,
                    "probe_cluster_description": "检索索引读取失败",
                    "probe_cluster_type": "error",
                    "confidence": 0.82,
                    "impact": 9,
                    "severity": 7.4,
                    "rank": 1,
                    "created_at": NOW,
                },
            ],
        )
        await session.execute(
            insert(probe_cluster_probes),
            [
                {"probe_cluster_id": "C2", "probe_id": "pr-050b-04"},
                {"probe_cluster_id": "C1", "probe_id": "pr-050b-03"},
            ],
        )
        if with_final:
            await session.execute(
                insert(evolution_finals).values(
                    run_id=RUN_ID,
                    best_version="v2.0.0-best",
                    verdict=True,
                    best_score=88.9,
                    init_score=84.3,
                    metrics=[
                        {
                            "name": "任务完成率",
                            "init": 78.0,
                            "best": 84.0,
                            "delta": 6.0,
                            "unit": "%",
                        },
                    ],
                ),
            )
    assert await repository.get_run(RUN_ID) is not None


async def test_list_cluster_probes_returns_cluster_sequence_order(
    step_database: tuple[Database, EvolutionRepository, ProbeQueryRepository],
) -> None:
    """Links read back in cluster seq then link insertion order."""
    database, repository, _ = step_database
    await _seed_clustered_run(database, repository)

    links = await repository.list_cluster_probes(RUN_ID)

    assert [(link.probe_cluster_id, link.probe_id) for link in links] == [
        ("C1", "pr-050b-03"),
        ("C2", "pr-050b-04"),
    ]


async def test_list_cluster_probes_is_empty_without_clusters(
    step_database: tuple[Database, EvolutionRepository, ProbeQueryRepository],
) -> None:
    """A preparing run has no links yet."""
    database, repository, _ = step_database
    await seed_external_corpus(database)
    await seed_run(database, progress_unit=0)

    assert await repository.list_cluster_probes(RUN_ID) == ()


async def test_get_final_returns_row_and_none(
    step_database: tuple[Database, EvolutionRepository, ProbeQueryRepository],
) -> None:
    """The terminal evaluation read is total: row when present, None otherwise."""
    database, repository, _ = step_database
    await _seed_clustered_run(database, repository, with_final=True)

    final = await repository.get_final(RUN_ID)
    assert final is not None
    assert final.best_version == "v2.0.0-best"
    assert final.verdict is True
    assert final.best_score == 88.9
    assert final.metrics == [
        {"name": "任务完成率", "init": 78.0, "best": 84.0, "delta": 6.0, "unit": "%"},
    ]

    assert await repository.get_final("evo-missing") is None


async def test_list_rows_by_ids_returns_joined_rows_without_hit_filtering(
    step_database: tuple[Database, EvolutionRepository, ProbeQueryRepository],
) -> None:
    """Explicit probe ids read back joined to case and session facts, probe-id ordered."""
    database, repository, probes = step_database
    await _seed_clustered_run(database, repository)

    rows = await probes.list_rows_by_ids(("pr-050b-04", "pr-050b-03"))

    assert [row.probe_id for row in rows] == ["pr-050b-03", "pr-050b-04"]
    first = rows[0]
    assert first.bad_case_id == "bc-050b-03"
    assert first.analysis_status == "analyzed_issue"
    assert first.probe_session_id == SESSION_ID
    assert first.probe_object == "deep-research"
    assert first.object_version == "v2.0.0"
    assert first.attribute_type == "error"
    assert first.session_title == "研究'用户数据驱动自进化'提到的所有方法"
    assert first.session_model == "glm-5.3"

    assert await probes.list_rows_by_ids(()) == ()


async def test_get_run_returns_none_for_unknown_id(
    step_database: tuple[Database, EvolutionRepository, ProbeQueryRepository],
) -> None:
    """Unknown run ids stay a repository concern returning None."""
    database, repository, _ = step_database
    await seed_external_corpus(database)
    await seed_run(database, progress_unit=0)

    assert await repository.get_run("evo-missing") is None
