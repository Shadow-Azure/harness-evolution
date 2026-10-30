"""Root-session traversal, payload writes, isolation, and replay semantics."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import func, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_sync import BadCaseRootSyncRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_cases, sync_runs, trajectory_payloads
from app.errors import AppError, ErrorCode
from app.service.acquisition.bad_case_sync import BadCaseRootSyncService
from app.third_party_api.session_query.models import SessionTrajectory
from app.utils.time import now_shanghai

ROOT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROOT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("bad-case-sync-service-test-secret"),
    )
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


async def _insert_bad_case(database: Database, root: str, suffix: str) -> None:
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            bad_cases.insert().values(
                bad_case_id=f"case-{suffix}",
                bad_case_session_id=root,
                bad_case_type="error",
                object_name="deep-research",
                object_type="skill",
                object_version="v1",
                bad_case_agent_id=None,
                title="case",
                bad_case_description="description",
                meta_data=None,
                source="test",
                created_at=now,
                updated_at=now,
            ),
        )


def _trajectory() -> SessionTrajectory:
    content = "\n".join(
        [
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-10-30T10:00:00+08:00",
                    "message": {"content": "prompt"},
                },
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": "2026-10-30T10:00:01+08:00",
                    "message": {"id": "m1", "model": "model", "content": []},
                },
            ),
        ],
    )
    return SessionTrajectory(content=content, line_count=2)


@dataclass
class FakeSource:
    tree: dict[str, tuple[str, ...]]
    failures: dict[str, Exception] | None = None
    calls: list[str] | None = None

    async def list_children(self, session_id: str) -> tuple[str, ...]:
        if self.calls is not None:
            self.calls.append(session_id)
        if self.failures and session_id in self.failures:
            raise self.failures[session_id]
        return self.tree.get(session_id, ())

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        return _trajectory()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_syncs_main_and_nested_subagents_with_parent_agent_meta(database: Database) -> None:
    await _insert_bad_case(database, ROOT_A, "a")
    source = FakeSource({ROOT_A: ("agent-a",), "agent-a": ("agent-b",)})
    service = BadCaseRootSyncService(
        database,
        BadCaseRootSyncRepository(database),
        source,
        batch_size=10,
        time_budget_seconds=60,
        max_agents=10,
        max_depth=5,
        lease_seconds=60,
    )

    result = await service.run(owner="job-1", now=now_shanghai())

    assert result.roots_synced == 1
    assert result.roots_failed == 0
    assert result.agents_fetched == 3
    assert result.payloads_inserted == 3

    async with database.session() as session:
        rows = (
            (
                await session.execute(
                    select(trajectory_payloads).where(
                        trajectory_payloads.c.root_session_id == ROOT_A,
                    ),
                )
            )
            .mappings()
            .all()
        )
    by_id = {row["agent_id"]: row for row in rows}
    assert set(by_id) == {ROOT_A, "agent-a", "agent-b"}
    assert by_id[ROOT_A]["agent_kind"] == "main"
    assert by_id[ROOT_A]["agent_meta"] is None
    assert by_id["agent-a"]["agent_kind"] == "subagent"
    assert by_id["agent-a"]["agent_meta"] == {"parentAgentId": ROOT_A}
    assert by_id["agent-b"]["agent_meta"] == {"parentAgentId": "agent-a"}
    assert all(row["source_type"] == "http_api" for row in rows)

    status = await BadCaseRootSyncRepository(database).get(ROOT_A)
    assert status is not None
    assert status.status == "synced"
    assert status.agent_count == 3


@pytest.mark.asyncio
async def test_duplicate_and_cyclic_children_do_not_repeat_agents(database: Database) -> None:
    await _insert_bad_case(database, ROOT_A, "a")
    source = FakeSource(
        {
            ROOT_A: ("agent-a", "agent-a"),
            "agent-a": (ROOT_A, "agent-b"),
            "agent-b": ("agent-a",),
        },
    )
    service = BadCaseRootSyncService(
        database,
        BadCaseRootSyncRepository(database),
        source,
        batch_size=10,
        time_budget_seconds=60,
        max_agents=10,
        max_depth=5,
        lease_seconds=60,
    )

    result = await service.run(owner="job-1", now=now_shanghai())

    assert result.agents_fetched == 3
    async with database.session() as session:
        count = (
            await session.execute(
                select(func.count()).where(
                    trajectory_payloads.c.root_session_id == ROOT_A,
                ),
            )
        ).scalar_one()
    assert count == 3


@pytest.mark.asyncio
async def test_one_root_failure_does_not_block_another_root(database: Database) -> None:
    await _insert_bad_case(database, ROOT_A, "a")
    await _insert_bad_case(database, ROOT_B, "b")
    now = now_shanghai()
    source = FakeSource(
        {ROOT_A: (), ROOT_B: ("agent-b",)},
        failures={
            ROOT_B: AppError(
                status_code=502,
                code=ErrorCode.SESSION_QUERY_TIMEOUT,
                message="timeout",
            )
        },
    )
    service = BadCaseRootSyncService(
        database,
        BadCaseRootSyncRepository(database),
        source,
        batch_size=10,
        time_budget_seconds=60,
        max_agents=10,
        max_depth=5,
        lease_seconds=60,
    )

    result = await service.run(owner="job-1", now=now)

    assert result.roots_synced == 1
    assert result.roots_failed == 1
    repository = BadCaseRootSyncRepository(database)
    synced = await repository.get(ROOT_A)
    failed = await repository.get(ROOT_B)
    assert synced is not None and synced.status == "synced"
    assert failed is not None and failed.status == "failed"
    assert failed.last_error == ErrorCode.SESSION_QUERY_TIMEOUT.value
    assert failed.next_retry_at is not None
    assert failed.next_retry_at >= now + timedelta(minutes=1)
    assert failed.agent_count == 1
    async with database.session() as session:
        partial = (
            await session.execute(
                select(func.count()).where(
                    trajectory_payloads.c.root_session_id == ROOT_B,
                ),
            )
        ).scalar_one()
    assert partial == 1


@pytest.mark.asyncio
async def test_depth_limit_marks_root_failed(database: Database) -> None:
    await _insert_bad_case(database, ROOT_A, "a")
    source = FakeSource({ROOT_A: ("agent-a",), "agent-a": ("agent-b",)})
    service = BadCaseRootSyncService(
        database,
        BadCaseRootSyncRepository(database),
        source,
        batch_size=10,
        time_budget_seconds=60,
        max_agents=10,
        max_depth=1,
        lease_seconds=60,
    )

    result = await service.run(owner="job-1", now=now_shanghai())

    assert result.roots_failed == 1
    status = await BadCaseRootSyncRepository(database).get(ROOT_A)
    assert status is not None
    assert status.status == "failed"
    assert status.last_error == ErrorCode.TRAVERSAL_LIMIT_EXCEEDED.value


@pytest.mark.asyncio
async def test_replay_runs_once_for_a_batch_with_payloads(database: Database) -> None:
    await _insert_bad_case(database, ROOT_A, "a")
    await _insert_bad_case(database, ROOT_B, "b")
    source = FakeSource({ROOT_A: (), ROOT_B: ()})
    service = BadCaseRootSyncService(
        database,
        BadCaseRootSyncRepository(database),
        source,
        batch_size=10,
        time_budget_seconds=60,
        max_agents=10,
        max_depth=5,
        lease_seconds=60,
    )

    result = await service.run(owner="job-1", now=now_shanghai())

    async with database.session() as session:
        runs = (await session.execute(select(func.count()).select_from(sync_runs))).scalar_one()
    assert runs == 1
    assert result.replayed >= 0


@pytest.mark.asyncio
async def test_no_candidates_writes_and_replays_nothing(database: Database) -> None:
    service = BadCaseRootSyncService(
        database,
        BadCaseRootSyncRepository(database),
        FakeSource({}),
        batch_size=10,
        time_budget_seconds=60,
        max_agents=10,
        max_depth=5,
        lease_seconds=60,
    )

    result = await service.run(owner="job-1", now=now_shanghai())

    assert result.roots_considered == 0
    assert result.payloads_inserted == 0
    async with database.session() as session:
        runs = (await session.execute(select(func.count()).select_from(sync_runs))).scalar_one()
    assert runs == 0
