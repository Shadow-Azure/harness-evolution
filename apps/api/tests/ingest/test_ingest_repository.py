"""Transactional repository rules for the workspace bad-case ingest."""

from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.db.crud.bad_case_ingest import (
    BadCaseIdConflict,
    BadCaseIngestRepository,
    BadCaseIngestRow,
    QuotaExceeded,
    WorkspaceMissing,
)
from app.db.crud.bad_case_sync import BadCaseRootSyncRepository
from app.db.models.domain import bad_case_root_sync
from app.utils.time import now_shanghai
from tests.ingest.helpers import (
    SESSION_ID,
    count_cases,
    create_ingest_workspace,
    ingest_body,
    report,
)


def ingest_row(**overrides: object) -> BadCaseIngestRow:
    """Return one normalized write row with targeted overrides."""
    values: dict[str, object] = {
        "bad_case_id": "BC-REPO-1",
        "session_id": SESSION_ID,
        "bad_case_type": "self",
        "object_name": "deep-research",
        "object_type": "skill",
        "object_version": "v2.4.0",
        "bad_case_agent_id": None,
        "title": "仓储层标题",
        "reason": "仓储层描述",
        "meta_data": {"file": "SKILL.md"},
        "source": "repo-test",
        "created_at": now_shanghai(),
    }
    values.update(overrides)
    return BadCaseIngestRow(**values)  # type: ignore[arg-type]


async def test_repository_rejects_an_unknown_workspace(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The transactional write fails closed when the workspace row is gone."""
    app, _client = ingest_client
    repository = BadCaseIngestRepository(app.state.database)

    with pytest.raises(WorkspaceMissing):
        await repository.ingest("ws-missing", ingest_row())


async def test_repository_quota_failure_leaves_no_partial_write(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The quota decision and the insert share one transaction."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Repo Quota", quota=1)
    await report(client, workspace, ingest_body())
    repository = BadCaseIngestRepository(app.state.database)

    with pytest.raises(QuotaExceeded) as rejected:
        await repository.ingest(workspace.workspace_id, ingest_row(bad_case_id="BC-REPO-2"))

    assert (rejected.value.quota, rejected.value.used) == (1, 1)
    assert await count_cases(app.state.database, workspace.workspace_id) == 1


async def test_repository_conflict_never_touches_the_owner_row(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A foreign workspace id raises before any update statement runs."""
    app, client = ingest_client
    owner = await create_ingest_workspace(app, client, name="Repo Owner", username="repo-owner")
    intruder = await create_ingest_workspace(
        app,
        client,
        name="Repo Intruder",
        username="repo-intruder",
    )
    await report(client, owner, ingest_body())
    repository = BadCaseIngestRepository(app.state.database)

    with pytest.raises(BadCaseIdConflict):
        await repository.ingest(
            intruder.workspace_id,
            ingest_row(bad_case_id="BC-HC-021", title="被覆盖的标题"),
        )

    row = await repository.read("BC-HC-021")
    assert row is not None
    assert row.workspace_id == owner.workspace_id
    assert row.title == "输出缺少来源校验"


async def test_repository_reports_created_flag_and_live_usage(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """`created` distinguishes 201 from 200 while usage stays a live count."""
    app, _client = ingest_client
    workspace = await create_ingest_workspace(app, _client, name="Repo Usage", quota=4)
    repository = BadCaseIngestRepository(app.state.database)

    first = await repository.ingest(workspace.workspace_id, ingest_row())
    second = await repository.ingest(
        workspace.workspace_id,
        ingest_row(title="第二版标题"),
    )

    assert (first.created, first.workspace_used) == (True, 1)
    assert (second.created, second.workspace_used) == (False, 1)
    stored = await repository.read("BC-REPO-1")
    assert stored is not None
    assert stored.title == "第二版标题"


async def test_ensure_pending_inserts_once_and_never_resets_state(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """`ensure_pending` is insert-if-absent for pending, synced, and failed rows."""
    app, client = ingest_client
    _workspace = await create_ingest_workspace(app, client, name="Repo Pending")
    repository = BadCaseRootSyncRepository(app.state.database)
    root = "22222222-2222-4222-8222-222222222222"

    created = await repository.ensure_pending(root)
    again = await repository.ensure_pending(root)
    state = await repository.get(root)
    assert created is True
    assert again is False
    assert state is not None
    assert state.status == "pending"

    synced_root = "33333333-3333-4333-8333-333333333333"
    now = now_shanghai()
    async with app.state.database.transaction() as session:
        await session.execute(
            bad_case_root_sync.insert().values(
                root_session_id=synced_root,
                status="synced",
                attempts=1,
                last_error=None,
                agent_count=3,
                started_at=now,
                synced_at=now,
                next_retry_at=None,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=now,
            ),
        )
    kept = await repository.ensure_pending(synced_root)
    synced = await repository.get(synced_root)
    assert kept is False
    assert synced is not None
    assert synced.status == "synced"
    assert synced.agent_count == 3
    assert synced.synced_at == now

    failed_root = "44444444-4444-4444-8444-444444444444"
    retry_at = now + timedelta(minutes=5)
    async with app.state.database.transaction() as session:
        await session.execute(
            bad_case_root_sync.insert().values(
                root_session_id=failed_root,
                status="failed",
                attempts=2,
                last_error="SYNC_FAILED: timeout",
                agent_count=0,
                started_at=now,
                synced_at=None,
                next_retry_at=retry_at,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=now,
            ),
        )
    kept_failed = await repository.ensure_pending(failed_root)
    failed = await repository.get(failed_root)
    assert kept_failed is False
    assert failed is not None
    assert failed.status == "failed"
    assert failed.last_error == "SYNC_FAILED: timeout"
    assert failed.next_retry_at == retry_at


async def test_repository_keeps_one_root_row_per_session(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Two cases under one root share a single pending marker."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Repo Root Once")
    repository = BadCaseIngestRepository(app.state.database)

    await repository.ingest(workspace.workspace_id, ingest_row())
    await repository.ingest(workspace.workspace_id, ingest_row(bad_case_id="BC-REPO-2"))

    async with app.state.database.session() as session:
        total = (
            await session.execute(
                select(func.count())
                .select_from(bad_case_root_sync)
                .where(bad_case_root_sync.c.root_session_id == SESSION_ID),
            )
        ).scalar_one()
    assert int(total) == 1
