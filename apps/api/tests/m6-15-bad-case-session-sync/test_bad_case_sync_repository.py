"""Durable bad-case root-sync status, claim, and statistics semantics."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_sync import BadCaseRootSyncRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_cases
from app.utils.time import now_shanghai

ROOT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROOT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ROOT_C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide a migrated SQLite database including external fixture tables."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("bad-case-sync-repository-test-secret"),
    )
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


async def _insert_bad_case(database: Database, root_session_id: str, suffix: str) -> None:
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            bad_cases.insert().values(
                bad_case_id=f"case-{suffix}",
                bad_case_session_id=root_session_id,
                bad_case_type="error",
                object_name="deep-research",
                object_type="skill",
                object_version="v1",
                bad_case_agent_id=None,
                title=f"case {suffix}",
                bad_case_description="description",
                meta_data=None,
                source="test",
                created_at=now,
                updated_at=now,
            ),
        )


@pytest.mark.asyncio
async def test_candidates_select_unsynced_failed_due_and_expired_syncing(
    database: Database,
) -> None:
    repository = BadCaseRootSyncRepository(database)
    now = now_shanghai()
    for root, suffix in ((ROOT_A, "a"), (ROOT_B, "b"), (ROOT_C, "c")):
        await _insert_bad_case(database, root, suffix)

    assert await repository.claim(ROOT_A, owner="job-1", lease_seconds=60, now=now)
    await repository.mark_synced(ROOT_A, agent_count=3, now=now)

    assert await repository.claim(ROOT_B, owner="job-1", lease_seconds=60, now=now)
    await repository.mark_failed(
        ROOT_B,
        error="SESSION_QUERY_TIMEOUT",
        next_retry_at=now + timedelta(minutes=5),
        now=now,
    )

    assert await repository.claim(ROOT_C, owner="job-1", lease_seconds=30, now=now)

    later = now + timedelta(minutes=6)
    candidates = await repository.list_candidates(later, limit=10)
    assert candidates == [ROOT_B, ROOT_C]
    assert await repository.count_candidates(later) == 2
    assert await repository.count_candidates(now) == 0

    stats = await repository.stats()
    assert stats.total == 3
    assert stats.synced == 1
    assert stats.syncing == 1
    assert stats.failed == 1
    assert stats.unsynced == 2


@pytest.mark.asyncio
async def test_expired_syncing_lease_is_reclaimable(database: Database) -> None:
    repository = BadCaseRootSyncRepository(database)
    now = now_shanghai()
    await _insert_bad_case(database, ROOT_A, "a")

    assert await repository.claim(ROOT_A, owner="job-1", lease_seconds=30, now=now)
    assert not await repository.claim(ROOT_A, owner="job-2", lease_seconds=30, now=now)

    later = now + timedelta(seconds=31)
    assert await repository.claim(ROOT_A, owner="job-2", lease_seconds=30, now=later)
    row = await repository.get(ROOT_A)
    assert row is not None
    assert row.status == "syncing"
    assert row.lease_owner == "job-2"
    assert row.attempts == 2


@pytest.mark.asyncio
async def test_failed_root_waits_for_next_retry_at(database: Database) -> None:
    repository = BadCaseRootSyncRepository(database)
    now = now_shanghai()
    await _insert_bad_case(database, ROOT_A, "a")
    assert await repository.claim(ROOT_A, owner="job-1", lease_seconds=30, now=now)
    await repository.mark_failed(
        ROOT_A,
        error="SESSION_QUERY_INVALID_RESPONSE",
        next_retry_at=now + timedelta(minutes=1),
        now=now,
    )

    assert await repository.list_candidates(now, limit=10) == []
    assert await repository.list_candidates(now + timedelta(minutes=1), limit=10) == [ROOT_A]


@pytest.mark.asyncio
async def test_stats_ignore_status_rows_for_roots_no_longer_in_bad_cases(
    database: Database,
) -> None:
    repository = BadCaseRootSyncRepository(database)
    now = now_shanghai()
    await _insert_bad_case(database, ROOT_A, "a")
    assert await repository.claim(ROOT_A, owner="job-1", lease_seconds=60, now=now)
    await repository.mark_synced(ROOT_A, agent_count=1, now=now)

    assert await repository.claim(ROOT_C, owner="job-1", lease_seconds=60, now=now)
    await repository.mark_synced(ROOT_C, agent_count=1, now=now)

    stats = await repository.stats()
    assert stats.total == 1
    assert stats.synced == 1
    assert stats.unsynced == 0


@pytest.mark.asyncio
async def test_missing_status_row_is_counted_and_selected(database: Database) -> None:
    """A bad_cases root with no status row is the normal unsynced case."""
    repository = BadCaseRootSyncRepository(database)
    now = now_shanghai()
    await _insert_bad_case(database, ROOT_A, "a")

    assert await repository.get(ROOT_A) is None
    assert await repository.list_candidates(now, limit=10) == [ROOT_A]
    assert await repository.count_candidates(now) == 1
    stats = await repository.stats()
    assert stats.total == 1
    assert stats.synced == 0
    assert stats.syncing == 0
    assert stats.failed == 0
    assert stats.unsynced == 1

    assert await repository.claim(ROOT_A, owner="job-1", lease_seconds=30, now=now)
    row = await repository.get(ROOT_A)
    assert row is not None
    assert row.status == "syncing"
    assert row.attempts == 1


@pytest.mark.asyncio
async def test_orphan_status_row_is_ignored_by_candidates_and_stats(database: Database) -> None:
    """A status row without a current bad_cases root remains audit-only."""
    repository = BadCaseRootSyncRepository(database)
    now = now_shanghai()
    assert await repository.claim(ROOT_C, owner="job-1", lease_seconds=60, now=now)
    await repository.mark_synced(ROOT_C, agent_count=2, now=now)

    assert await repository.list_candidates(now, limit=10) == []
    assert await repository.count_candidates(now) == 0
    stats = await repository.stats()
    assert stats.total == 0
    assert stats.synced == 0
    assert stats.syncing == 0
    assert stats.failed == 0
    assert stats.unsynced == 0


@pytest.mark.asyncio
async def test_new_bad_case_for_synced_root_does_not_requeue(database: Database) -> None:
    """A second problem on an already-synced root reuses the existing payloads."""
    repository = BadCaseRootSyncRepository(database)
    now = now_shanghai()
    await _insert_bad_case(database, ROOT_A, "a")
    assert await repository.claim(ROOT_A, owner="job-1", lease_seconds=30, now=now)
    await repository.mark_synced(ROOT_A, agent_count=1, now=now)

    await _insert_bad_case(database, ROOT_A, "a2")
    assert await repository.list_candidates(now, limit=10) == []
    stats = await repository.stats()
    assert stats.total == 1
    assert stats.synced == 1
    assert stats.unsynced == 0


@pytest.mark.asyncio
async def test_mark_synced_recomputes_and_clears_retry_state(database: Database) -> None:
    repository = BadCaseRootSyncRepository(database)
    now = now_shanghai()
    await _insert_bad_case(database, ROOT_A, "a")
    assert await repository.claim(ROOT_A, owner="job-1", lease_seconds=30, now=now)
    await repository.mark_failed(
        ROOT_A,
        error="SESSION_QUERY_TIMEOUT",
        next_retry_at=now + timedelta(minutes=5),
        now=now,
    )
    later = now + timedelta(minutes=5)
    assert await repository.claim(ROOT_A, owner="job-2", lease_seconds=30, now=later)
    await repository.mark_synced(ROOT_A, agent_count=4, now=later)

    row = await repository.get(ROOT_A)
    assert row is not None
    assert row.status == "synced"
    assert row.agent_count == 4
    assert row.last_error is None
    assert row.next_retry_at is None
    assert row.lease_owner is None
    assert row.lease_expires_at is None
    assert row.synced_at is not None
