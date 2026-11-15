"""Transactional repository rules for the workspace bad-case ingest."""

from datetime import datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.crud.bad_case_ingest import (
    BadCaseIdConflict,
    BadCaseIngestRepository,
    BadCaseIngestRow,
    QuotaExceeded,
    WorkspaceMissing,
)
from app.db.crud.bad_case_sync import (
    BadCaseRootSyncRepository,
    insert_pending_root,
)
from app.db.models.domain import bad_case_root_sync
from app.errors import AppError, ErrorCode
from app.service.workspaces.ingest import BadCaseIngest, BadCaseIngestService
from app.service.workspaces.service import WorkspaceCredentialAccess
from app.utils.time import now_shanghai
from tests.ingest.helpers import (
    SESSION_ID,
    count_cases,
    create_ingest_workspace,
    ingest_body,
    report,
)


class _BlindFirstOwnerRepository(BadCaseIngestRepository):
    """Report the first ownership read as a miss while a winner is committed.

    SQLite takes the database write lock before the ownership read, so a real
    two-connection race cannot reach ``_insert``'s fallback locally; making the
    read blind is how the test reaches the same interleaving the fallback
    exists for.
    """

    def __init__(self, database: Database) -> None:
        """Start with one undelivered ownership miss."""
        super().__init__(database)
        self._first_read = True

    async def _existing_owner(self, session: AsyncSession, bad_case_id: str) -> str | None:
        """Return ``None`` once, then delegate to the real read."""
        if self._first_read:
            self._first_read = False
            return None
        return await super()._existing_owner(session, bad_case_id)


class _InterleavedRootSyncRepository(BadCaseRootSyncRepository):
    """Insert a pending row between ``claim``'s read and its state insert.

    This is the interleaving a concurrent report creates on MySQL: the claim
    sees no state row, then the report's insert-if-absent commits first.
    """

    async def _start_syncing(
        self,
        session: AsyncSession,
        root_session_id: str,
        *,
        owner: str,
        now_value: datetime,
        expires_at: datetime,
    ) -> bool:
        """Commit the pending row first, then let the claim's insert collide."""
        await insert_pending_root(session, root_session_id, now=now_shanghai())
        return await super()._start_syncing(
            session,
            root_session_id,
            owner=owner,
            now_value=now_value,
            expires_at=expires_at,
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


async def test_service_maps_a_vanished_workspace_to_not_found(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """`WorkspaceMissing` at the write boundary becomes 404 at the service."""
    app, _client = ingest_client
    service = BadCaseIngestService(
        BadCaseIngestRepository(app.state.database),
        app.state.workspaces,
    )
    access = WorkspaceCredentialAccess(
        workspace_id="ws-vanished",
        credential_id="cred-vanished",
    )
    body = BadCaseIngest.model_validate(ingest_body())

    with pytest.raises(AppError) as rejected:
        await service.ingest(access, body)

    assert (rejected.value.status_code, rejected.value.code) == (
        404,
        ErrorCode.WORKSPACE_NOT_FOUND,
    )


async def test_insert_fallback_degrades_a_same_workspace_race_to_an_update(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A primary-key race inside one workspace updates the winner and returns 200."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Repo Race Same", quota=2)
    winner = await report(
        client,
        workspace,
        ingest_body(badCaseId="BC-RACE-SAME", title="并发赢家"),
    )
    assert winner.status_code == 201
    repository = _BlindFirstOwnerRepository(app.state.database)

    write = await repository.ingest(
        workspace.workspace_id,
        ingest_row(bad_case_id="BC-RACE-SAME", title="落败者改写"),
    )

    assert (write.created, write.workspace_used) == (False, 1)
    stored = await repository.read("BC-RACE-SAME")
    assert stored is not None
    assert stored.workspace_id == workspace.workspace_id
    assert stored.title == "落败者改写"


async def test_insert_fallback_refuses_a_foreign_workspace_race(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The same race across workspaces surfaces as 409, never a raw 500."""
    app, client = ingest_client
    owner = await create_ingest_workspace(
        app,
        client,
        name="Repo Race Owner",
        username="race-owner",
    )
    intruder = await create_ingest_workspace(
        app,
        client,
        name="Repo Race Intruder",
        username="race-intruder",
    )
    assert (
        await report(
            client,
            owner,
            ingest_body(badCaseId="BC-RACE-FOREIGN", title="赢家标题"),
        )
    ).status_code == 201
    repository = _BlindFirstOwnerRepository(app.state.database)
    service = BadCaseIngestService(repository, app.state.workspaces)
    body = BadCaseIngest.model_validate(
        ingest_body(badCaseId="BC-RACE-FOREIGN", title="入侵标题"),
    )

    with pytest.raises(AppError) as rejected:
        await service.ingest(
            WorkspaceCredentialAccess(
                workspace_id=intruder.workspace_id,
                credential_id="cred-intruder",
            ),
            body,
        )

    assert (rejected.value.status_code, rejected.value.code) == (
        409,
        ErrorCode.BAD_CASE_ID_CONFLICT,
    )
    stored = await repository.read("BC-RACE-FOREIGN")
    assert stored is not None
    assert stored.workspace_id == owner.workspace_id
    assert stored.title == "赢家标题"


async def test_claim_tolerates_a_concurrent_pending_insert(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A pending row that lands after the claim's read is not an error."""
    app, _client = ingest_client
    repository = _InterleavedRootSyncRepository(app.state.database)
    root = "55555555-5555-4555-8555-555555555555"
    now = now_shanghai()

    claimed = await repository.claim(root, owner="tick-1", lease_seconds=60, now=now)
    state = await repository.get(root)
    next_tick = await repository.claim(root, owner="tick-2", lease_seconds=60, now=now)

    assert claimed is False
    assert state is not None
    assert state.status == "pending"
    assert state.attempts == 0
    assert next_tick is True
