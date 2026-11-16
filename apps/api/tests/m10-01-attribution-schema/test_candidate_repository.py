"""Evolution run candidate snapshot repository contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.attributions import CandidateWrite, EvolutionRunCandidateRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_cases, probe_reports
from app.db.models.evolution import evolution_run_candidates, evolution_runs
from app.utils.time import SHANGHAI

NOW = datetime(2026, 11, 17, 9, tzinfo=SHANGHAI)
LATER = datetime(2026, 11, 17, 10, tzinfo=SHANGHAI)
SESSION_ID = "95000000-0000-4000-8000-000000000001"
RUN_ID = "run-candidate-a"
CASE_A = "bc-candidate-a"
CASE_B = "bc-candidate-b"


@pytest_asyncio.fixture
async def candidate_repository(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRunCandidateRepository]]:
    """Provide a migrated SQLite database with one run and two cases."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'candidate-repository.db'}",
        ),
    )
    await database.start()
    await upgrade_database(database)
    async with database.transaction() as session:
        await session.execute(
            evolution_runs.insert().values(
                id=RUN_ID,
                title="候选测试",
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
        for case_id in (CASE_A, CASE_B):
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
        await session.execute(
            probe_reports.insert().values(
                probe_id="probe-candidate",
                workspace_id="ws-default",
                session_id=SESSION_ID,
                probe_type="skill",
                probe_object="deep-research",
                object_version="v2.0.0",
                attribute_type="prompt",
                conclusion="attributed",
                confidence=0.8,
                probe_description="candidate probe",
                probe_analysis="analysis",
                policy_version="v1",
                attribution_engine="engine-a",
                cache_key="c" * 64,
                created_at=NOW,
                updated_at=NOW,
            ),
        )
    try:
        yield database, EvolutionRunCandidateRepository(database)
    finally:
        await database.dispose()


def candidate_write(
    candidate_id: str = "candidate-a",
    *,
    bad_case_id: str = CASE_A,
    included: bool = True,
    included_reason: str = "self_report",
    order_state: str = "comparable",
    probe_id: str | None = None,
    is_cached: bool = False,
    created_at: datetime = NOW,
) -> CandidateWrite:
    """Build one candidate snapshot with deterministic defaults."""
    return CandidateWrite(
        id=candidate_id,
        run_id=RUN_ID,
        workspace_id="ws-default",
        session_id=SESSION_ID,
        bad_case_id=bad_case_id,
        object_trigger_agent_id="agent-object",
        object_trigger_event_index=3,
        object_trigger_at=NOW,
        case_trigger_agent_id="agent-case",
        case_trigger_event_index=7,
        case_trigger_at=LATER,
        order_state=cast(Any, order_state),
        included=included,
        included_reason=cast(Any, included_reason),
        probe_id=probe_id,
        is_cached=is_cached,
        created_at=created_at,
    )


async def test_candidates_persist_included_and_excluded_rows(
    candidate_repository: tuple[Database, EvolutionRunCandidateRepository],
) -> None:
    """Every candidate is stored, including the policy-excluded ones."""
    _database, repository = candidate_repository
    await repository.upsert(candidate_write())
    await repository.upsert(
        candidate_write(
            "candidate-b",
            bad_case_id=CASE_B,
            included=False,
            included_reason="policy_excluded",
            order_state="unknown",
        ),
    )

    records = await repository.list(RUN_ID)
    assert await repository.count(RUN_ID) == 2
    assert await repository.count("run-candidate-missing") == 0
    assert [record.bad_case_id for record in records] == [CASE_A, CASE_B]
    assert records[0].included is True
    assert records[0].included_reason == "self_report"
    assert records[0].order_state == "comparable"
    assert records[1].included is False
    assert records[1].included_reason == "policy_excluded"
    assert records[1].order_state == "unknown"


async def test_candidate_upsert_is_idempotent_per_run_and_case(
    candidate_repository: tuple[Database, EvolutionRunCandidateRepository],
) -> None:
    """Re-preparing a run updates the row in place and keeps its identity."""
    database, repository = candidate_repository
    await repository.upsert(candidate_write())
    await repository.upsert(
        replace(
            candidate_write(),
            included=False,
            included_reason="both",
            is_cached=True,
            probe_id="probe-candidate",
            object_trigger_event_index=9,
        ),
    )

    async with database.session() as session:
        count = int(
            (
                await session.execute(
                    select(func.count()).select_from(evolution_run_candidates),
                )
            ).scalar_one(),
        )
        row = (await session.execute(select(evolution_run_candidates))).mappings().one()
    assert count == 1
    records = await repository.list(RUN_ID)
    assert len(records) == 1
    record = records[0]
    assert record.id == "candidate-a"
    assert record.included is False
    assert record.included_reason == "both"
    assert record.is_cached is True
    assert record.probe_id == "probe-candidate"
    assert record.object_trigger_event_index == 9
    assert record.created_at == NOW
    assert row["created_at"] == NOW.replace(tzinfo=None)


async def test_candidate_rejects_unknown_closed_values(
    candidate_repository: tuple[Database, EvolutionRunCandidateRepository],
) -> None:
    """Unknown order states and inclusion reasons fail before any write."""
    with pytest.raises(ValueError, match="order_state"):
        candidate_write(order_state="later")
    with pytest.raises(ValueError, match="included_reason"):
        candidate_write(included_reason="unknown_reason")


async def test_candidate_list_is_scoped_to_one_run(
    candidate_repository: tuple[Database, EvolutionRunCandidateRepository],
) -> None:
    """Listing one run never leaks another run's candidates."""
    database, repository = candidate_repository
    async with database.transaction() as session:
        await session.execute(
            evolution_runs.insert().values(
                id="run-candidate-other",
                title="其它 run",
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
    await repository.upsert(candidate_write())
    await repository.upsert(
        replace(candidate_write("candidate-other"), run_id="run-candidate-other"),
    )

    assert [record.id for record in await repository.list(RUN_ID)] == ["candidate-a"]
    assert [record.id for record in await repository.list("run-candidate-other")] == [
        "candidate-other"
    ]
