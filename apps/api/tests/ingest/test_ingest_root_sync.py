"""Root-session discoverability after an ingest write."""

from datetime import timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select

from app.db.crud.bad_case_sync import BadCaseRootSyncRepository
from app.db.models.domain import bad_case_root_sync
from app.utils.time import now_shanghai
from tests.ingest.helpers import (
    SESSION_ID,
    create_ingest_workspace,
    ingest_body,
    report,
)


async def test_new_root_session_becomes_a_sync_candidate(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A first report inserts a pending root-sync row the scheduler can claim."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Root Pending")
    repository = BadCaseRootSyncRepository(app.state.database)

    response = await report(client, workspace, ingest_body())

    assert response.status_code == 201
    state = await repository.get(SESSION_ID)
    assert state is not None
    assert state.status == "pending"
    assert state.attempts == 0
    assert state.agent_count == 0
    assert state.lease_owner is None
    assert SESSION_ID in await repository.list_candidates(now_shanghai(), limit=10)


async def test_synced_root_is_never_reset_by_later_reports(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """`synced` is absorbing: new bad cases under the root do not force a refetch."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Root Synced")
    repository = BadCaseRootSyncRepository(app.state.database)
    await report(client, workspace, ingest_body())
    now = now_shanghai()
    await repository.mark_synced(SESSION_ID, agent_count=2, now=now)
    synced = await repository.get(SESSION_ID)
    assert synced is not None

    await report(client, workspace, ingest_body(badCaseId="BC-HC-022"))

    state = await repository.get(SESSION_ID)
    assert state is not None
    assert state.status == "synced"
    assert state.agent_count == 2
    assert state.attempts == synced.attempts
    assert state.synced_at == synced.synced_at
    assert SESSION_ID not in await repository.list_candidates(now_shanghai(), limit=10)


async def test_failed_root_keeps_its_backoff_after_later_reports(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A reported case never shortens an existing retry backoff."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Root Failed")
    repository = BadCaseRootSyncRepository(app.state.database)
    await report(client, workspace, ingest_body())
    now = now_shanghai()
    retry_at = now + timedelta(minutes=30)
    await repository.mark_failed(
        SESSION_ID,
        error="SYNC_FAILED: upstream unavailable",
        next_retry_at=retry_at,
        now=now,
    )

    await report(client, workspace, ingest_body(badCaseId="BC-HC-022"))

    state = await repository.get(SESSION_ID)
    assert state is not None
    assert state.status == "failed"
    assert state.last_error == "SYNC_FAILED: upstream unavailable"
    assert state.next_retry_at is not None
    assert state.next_retry_at == retry_at
    assert SESSION_ID not in await repository.list_candidates(now_shanghai(), limit=10)


async def test_repeat_reports_do_not_duplicate_root_rows(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Re-reporting one case leaves exactly one root-sync row for its session."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Root Repeat")

    await report(client, workspace, ingest_body())
    await report(client, workspace, ingest_body(title="重报"))
    await report(client, workspace, ingest_body(badCaseId="BC-HC-022"))

    async with app.state.database.session() as session:
        total = (
            await session.execute(
                select(func.count())
                .select_from(bad_case_root_sync)
                .where(bad_case_root_sync.c.root_session_id == SESSION_ID),
            )
        ).scalar_one()
    assert int(total) == 1
