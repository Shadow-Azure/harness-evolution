"""V2 rows stay readable through the legacy problem service and probe preview."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import insert, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_cases import BadCaseRepository
from app.db.crud.probe_query import ProbeHitQuery, ProbeHitRow, ProbeQueryRepository
from app.db.crud.problems import ProblemRepository
from app.db.crud.read_scope import WorkspaceReadScope
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agents,
    bad_case_analysis,
    bad_cases,
    probe_reports,
    session_families,
    source_records,
)
from app.service.bad_cases.service import BadCaseService
from app.service.evolution.probe_query import probe_row_of
from app.service.problems.service import ProblemService
from app.utils.time import SHANGHAI

NOW = datetime(2026, 11, 17, 14, tzinfo=SHANGHAI)
LATER = datetime(2026, 11, 17, 15, tzinfo=SHANGHAI)
SESSION_ID = "97000000-0000-4000-8000-000000000001"
OTHER_SESSION_ID = "97000000-0000-4000-8000-000000000002"
MULTI_CASE_ID = "bc-v2-multi"
NON_TARGET_CASE_ID = "bc-v2-non-target"
MISMATCH_CASE_ID = "bc-v2-mismatch"
V1_PROBE_ID = "probe-v1-multi"
ATTR_PROBE_ID = "probe-v2-attributed"
NON_TARGET_PROBE_ID = "probe-v2-non-target"
MISMATCH_PROBE_ID = "probe-v2-mismatch"
OBJECT_NAME = "deep-research"
OBJECT_VERSION = "v2.0.0"


def _probe_values(
    probe_id: str,
    *,
    session_id: str = SESSION_ID,
    conclusion: str = "attributed",
    attribute_type: str | None = "prompt",
    description: str,
    cache_key: str,
) -> dict[str, object]:
    """Build one V2 probe row with deterministic attribution facts."""
    return {
        "probe_id": probe_id,
        "workspace_id": "ws-default",
        "session_id": session_id,
        "probe_type": "skill",
        "probe_object": OBJECT_NAME,
        "object_version": OBJECT_VERSION,
        "attribute_type": attribute_type,
        "conclusion": conclusion,
        "confidence": 0.8,
        "probe_description": description,
        "probe_analysis": "analysis",
        "policy_version": "v1",
        "attribution_engine": "engine-a",
        "cache_key": cache_key,
        "created_at": NOW,
        "updated_at": NOW,
    }


@pytest_asyncio.fixture
async def problem_service(tmp_path: Path) -> AsyncIterator[tuple[Database, ProblemService]]:
    """Provide a migrated database with V1 and V2 attribution rows."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'v2-legacy-reads.db'}",
        ),
    )
    await database.start()
    await upgrade_database(database)
    async with database.transaction() as session:
        await session.execute(
            insert(source_records).values(
                runtime_key="claude-code",
                root_session_id=SESSION_ID,
                agent_id=SESSION_ID,
                kind="main",
                source_type="script",
                line_count=1,
                received_at=NOW,
                processed_at=NOW,
                processed_hash="b" * 64,
                parser_version=5,
                last_sync_run_id=None,
            ),
        )
        source_id = int(
            (
                await session.execute(
                    select(source_records.c.id).where(
                        source_records.c.root_session_id == SESSION_ID,
                    ),
                )
            ).scalar_one(),
        )
        await session.execute(
            insert(session_families).values(
                id=SESSION_ID,
                runtime_key="claude-code",
                short_title="V2 compatibility",
                title="V2 compatibility",
                search_text="v2 compatibility",
                repo_name="repo",
                project_path="/workspace/repo",
                git_branch=None,
                cli_version="2.0.1",
                entrypoint=None,
                model="model-main",
                models=["model-main"],
                started_at=NOW,
                ended_at=NOW,
                duration_seconds=0,
                status="completed",
                skill_names=[],
                user_turns_count=0,
                messages_count=0,
                tools_count=0,
                errors_count=0,
                agents_count=0,
                tokens_total=0,
                source_type="script",
                main_record_id=source_id,
                imported_at=NOW,
                updated_at=NOW,
            ),
        )
        await session.execute(
            insert(agents).values(
                id=SESSION_ID,
                runtime_key="claude-code",
                root_session_id=SESSION_ID,
                parent_agent_id=None,
                kind="main",
                requested_model="model-main",
                spawn_depth=0,
                lines=1,
                messages_count=0,
                tokens_total=0,
                tools_count=0,
                errors_count=0,
                sort_key=0,
                tree_index=0,
            ),
        )
        for case_id in (MULTI_CASE_ID, NON_TARGET_CASE_ID, MISMATCH_CASE_ID):
            await session.execute(
                insert(bad_cases).values(
                    bad_case_id=case_id,
                    bad_case_session_id=SESSION_ID,
                    bad_case_type="self",
                    object_name=OBJECT_NAME,
                    object_type="skill",
                    object_version=OBJECT_VERSION,
                    bad_case_agent_id=None,
                    title=case_id,
                    bad_case_description="reason",
                    meta_data=None,
                    source="fixtures",
                    created_at=NOW,
                    updated_at=NOW,
                ),
            )
        await session.execute(
            insert(probe_reports),
            [
                _probe_values(
                    V1_PROBE_ID,
                    description="legacy issue",
                    cache_key="1" * 64,
                ),
                _probe_values(
                    ATTR_PROBE_ID,
                    description="v2 attributed",
                    cache_key="2" * 64,
                ),
                _probe_values(
                    NON_TARGET_PROBE_ID,
                    conclusion="non_target",
                    attribute_type=None,
                    description="v2 not this object",
                    cache_key="3" * 64,
                ),
                _probe_values(
                    MISMATCH_PROBE_ID,
                    session_id=OTHER_SESSION_ID,
                    description="v2 wrong session",
                    cache_key="4" * 64,
                ),
            ],
        )
        await session.execute(
            insert(bad_case_analysis),
            [
                {
                    "bad_case_id": MULTI_CASE_ID,
                    "analysis_status": "analyzed_issue",
                    "probe_id": V1_PROBE_ID,
                    "analysis_result": {"summary": "legacy issue"},
                    "updated_at": NOW,
                },
                {
                    "bad_case_id": MULTI_CASE_ID,
                    "analysis_status": None,
                    "probe_id": ATTR_PROBE_ID,
                    "analysis_result": None,
                    "updated_at": LATER,
                },
                {
                    "bad_case_id": NON_TARGET_CASE_ID,
                    "analysis_status": None,
                    "probe_id": NON_TARGET_PROBE_ID,
                    "analysis_result": None,
                    "updated_at": NOW,
                },
                {
                    "bad_case_id": MISMATCH_CASE_ID,
                    "analysis_status": None,
                    "probe_id": MISMATCH_PROBE_ID,
                    "analysis_result": None,
                    "updated_at": NOW,
                },
            ],
        )
    service = ProblemService(
        ProblemRepository(database),
        BadCaseService(BadCaseRepository(database)),
    )
    try:
        yield database, service
    finally:
        await database.dispose()


async def test_problem_service_maps_v2_attributed_rows(
    problem_service: tuple[Database, ProblemService],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A NULL legacy status with an attributed probe stays an analyzed issue."""
    _database, service = problem_service
    caplog.set_level(logging.WARNING)

    analysis = await service.get_analysis(
        MULTI_CASE_ID,
        SESSION_ID,
        WorkspaceReadScope.all_workspaces(),
    )

    assert analysis.root.status == "analyzed_issue"
    assert analysis.root.probe_id == ATTR_PROBE_ID
    assert analysis.root.attribute_type == "prompt"
    assert analysis.root.display_state == "analyzed_issue_prompt"
    assert analysis.root.result is not None
    assert analysis.root.result.model_dump() == {"summary": "v2 attributed"}
    assert "external analysis status is invalid" not in caplog.text


async def test_problem_service_maps_v2_non_target_rows(
    problem_service: tuple[Database, ProblemService],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A NULL legacy status with a non-target probe becomes analyzed_nonissue."""
    _database, service = problem_service
    caplog.set_level(logging.WARNING)

    analysis = await service.get_analysis(
        NON_TARGET_CASE_ID,
        SESSION_ID,
        WorkspaceReadScope.all_workspaces(),
    )

    assert analysis.root.status == "analyzed_nonissue"
    assert analysis.root.probe_id is None
    assert analysis.root.attribute_type is None
    assert analysis.root.display_state == "analyzed_nonissue"
    assert analysis.root.result is not None
    assert analysis.root.result.model_dump() == {
        "reason": "v2 not this object",
        "reasoning": [],
    }
    assert "external analysis status is invalid" not in caplog.text


async def test_problem_service_keeps_session_mismatch_warning(
    problem_service: tuple[Database, ProblemService],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A V2 row pointing at another session's probe still degrades with a warning."""
    _database, service = problem_service
    caplog.set_level(logging.WARNING)

    analysis = await service.get_analysis(
        MISMATCH_CASE_ID,
        SESSION_ID,
        WorkspaceReadScope.all_workspaces(),
    )

    assert analysis.root.status == "unanalyzed"
    assert "external probe belongs to a different session" in caplog.text


async def test_probe_preview_keeps_attributed_and_drops_non_target(
    problem_service: tuple[Database, ProblemService],
) -> None:
    """The wizard preview maps V2 statuses and never renders non-target probes."""
    database, _service = problem_service
    repository = ProbeQueryRepository(database)
    query = ProbeHitQuery(
        target_type="skill",
        target_name=OBJECT_NAME,
        target_version=OBJECT_VERSION,
        window_from=None,
        window_to=None,
        models=(),
        workspace_ids=None,
    )

    rows = await repository.list_hit_rows(query)
    by_probe: dict[str, list[ProbeHitRow]] = {}
    for row in rows:
        by_probe.setdefault(row.probe_id, []).append(row)

    non_target_rows = by_probe[NON_TARGET_PROBE_ID]
    assert non_target_rows[0].analysis_status == "analyzed_nonissue"
    assert non_target_rows[0].attribute_type is None
    assert probe_row_of(non_target_rows) is None

    attributed_rows = by_probe[ATTR_PROBE_ID]
    assert attributed_rows[0].analysis_status == "analyzed_issue"
    item = probe_row_of(attributed_rows)
    assert item is not None
    assert item.probe_id == ATTR_PROBE_ID
    assert item.attribute_type == "prompt"
    assert item.description == "v2 attributed"


async def test_problem_repository_related_orders_multi_rows_stably(
    problem_service: tuple[Database, ProblemService],
) -> None:
    """The public snapshot keeps all rows and the newest one last for the map."""
    database, _service = problem_service
    repository = ProblemRepository(database)

    snapshot = await repository.case_snapshot(
        MULTI_CASE_ID,
        WorkspaceReadScope.all_workspaces(),
    )

    assert snapshot is not None
    assert [row.probe_id for row in snapshot.analyses] == [V1_PROBE_ID, ATTR_PROBE_ID]
    assert [row.updated_at for row in snapshot.analyses] == [NOW, LATER]
