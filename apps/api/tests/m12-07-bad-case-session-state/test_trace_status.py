"""m12-07: a reported case stays visible while its Session trace is not ready."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, select, update

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_sync import (
    BadCaseRootSyncRepository,
    BadCaseRootSyncRow,
    insert_pending_root,
)
from app.db.crud.fixtures import run_corpus_seed
from app.db.models.domain import bad_case_root_sync, bad_cases
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.fixture_corpus import load_fixture_corpus
from app.main import create_app
from app.service.bad_cases.session_status import classify_trace_status
from app.third_party_api.bad_case_query.models import BadCasePage
from app.utils.time import now_shanghai
from tests.bad_case_sync_fakes import StubBadCaseSyncSource

ROOT = Path(__file__).resolve().parents[4]
READY_SESSION = "10000000-0000-4000-8000-000000000001"
OTHER_SESSION = "10000000-0000-4000-8000-000000000002"
PENDING_ROOT = "30000000-0000-4000-8000-000000000101"
PENDING_ROW_ROOT = "30000000-0000-4000-8000-000000000102"
SYNCING_ROOT = "30000000-0000-4000-8000-000000000103"
FAILED_ROOT = "30000000-0000-4000-8000-000000000104"
UNAVAILABLE_ROOT = "30000000-0000-4000-8000-000000000105"
SYNCED_LOST_ROOT = "30000000-0000-4000-8000-000000000106"
MISSING_CASE = "case-m12-07-missing"


@dataclass(frozen=True, slots=True)
class StatusEnvironment:
    """Authenticated client plus the seeded workspace database."""

    client: httpx.AsyncClient
    database: Database
    authorization: dict[str, str]


async def _login(client: httpx.AsyncClient) -> dict[str, str]:
    """Seed an admin, change the bootstrap password, and return a bearer header."""
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "initial-password"},
    )
    assert login.status_code == 200
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
        json={
            "oldPassword": "initial-password",
            "newPassword": "replacement-password",
        },
    )
    assert changed.status_code == 204
    authenticated = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "replacement-password"},
    )
    assert authenticated.status_code == 200
    return {"Authorization": f"Bearer {authenticated.json()['accessToken']}"}


def _case(case_id: str, root_session_id: str, *, created_at: Any) -> dict[str, Any]:
    """Build one reported case owned by the default workspace."""
    return {
        "bad_case_id": case_id,
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "bad_case_session_id": root_session_id,
        "bad_case_type": "self",
        "object_name": "deep-research",
        "object_type": "skill",
        "object_version": "v1",
        "bad_case_agent_id": None,
        "title": f"Case {case_id}",
        "bad_case_description": "m12-07 trace state fixture.",
        "meta_data": None,
        "source": "tests",
        "created_at": created_at,
        "updated_at": created_at,
    }


def _state(
    root_session_id: str,
    *,
    status: str,
    last_error: str | None,
    next_retry_at: Any = None,
    source_kind: str = "global",
    attempts: int = 1,
) -> dict[str, Any]:
    """Build one durable root-sync row with a stable status and error."""
    now = now_shanghai()
    return {
        "root_session_id": root_session_id,
        "status": status,
        "source_kind": source_kind,
        "source_snapshot": {"kind": source_kind},
        "attempts": attempts,
        "last_error": last_error,
        "agent_count": 0,
        "started_at": now,
        "synced_at": now if status == "synced" else None,
        "next_retry_at": next_retry_at,
        "lease_owner": None,
        "lease_expires_at": None,
        "updated_at": now,
    }


async def _seed_status_rows(database: Database) -> None:
    """Add five trace states next to the corpus' normalized Session."""
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            insert(bad_cases),
            [
                _case("case-ready-m12-07", READY_SESSION, created_at=now),
                _case("case-pending-m12-07", PENDING_ROOT, created_at=now),
                _case("case-pending-row-m12-07", PENDING_ROW_ROOT, created_at=now),
                _case("case-syncing-m12-07", SYNCING_ROOT, created_at=now),
                _case("case-failed-m12-07", FAILED_ROOT, created_at=now),
                _case("case-unavailable-m12-07", UNAVAILABLE_ROOT, created_at=now),
                _case("case-synced-lost-m12-07", SYNCED_LOST_ROOT, created_at=now),
            ],
        )
        await session.execute(
            insert(bad_case_root_sync),
            [
                _state(READY_SESSION, status="synced", last_error=None),
                _state(
                    PENDING_ROW_ROOT,
                    status="pending",
                    last_error=None,
                ),
                _state(
                    SYNCING_ROOT,
                    status="syncing",
                    last_error=None,
                ),
                _state(
                    FAILED_ROOT,
                    status="failed",
                    last_error="SESSION_QUERY_TIMEOUT",
                    next_retry_at=now - timedelta(minutes=1),
                ),
                _state(
                    UNAVAILABLE_ROOT,
                    status="failed",
                    last_error="SESSION_QUERY_UNAVAILABLE",
                    next_retry_at=now - timedelta(minutes=1),
                ),
                _state(SYNCED_LOST_ROOT, status="synced", last_error=None),
            ],
        )


class _FakeSyncSource(StubBadCaseSyncSource):
    """Keep the trace-status fixture independent of any upstream HTTP call."""

    provider = "fake"

    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        return BadCasePage(total=0, offset=offset, limit=limit, items=())


@pytest_asyncio.fixture
async def trace_status(tmp_path: Path) -> AsyncIterator[StatusEnvironment]:
    """Seed the corpus plus the five derived trace states as a global admin."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("m12-07-trace-status-signing-secret-length"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
        session_query_base_url="http://127.0.0.1:9/session-query",
        session_query_token=SecretStr("m12-07-query-token"),
        sync_interval_seconds=0,
    )
    corpus = load_fixture_corpus(ROOT / "fixtures" / "m2-synthetic" / "corpus.json")
    await run_corpus_seed(settings, corpus)
    app = create_app(settings, bad_case_sync_source=_FakeSyncSource())
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        database = app.state.database
        await _seed_status_rows(database)
        yield StatusEnvironment(
            client=client,
            database=database,
            authorization=await _login(client),
        )


async def _detail(
    environment: StatusEnvironment,
    case_id: str,
) -> httpx.Response:
    """Read one case through the workspace detail route."""
    return await environment.client.get(
        f"/api/workspaces/{DEFAULT_WORKSPACE_ID}/bad-cases/{case_id}",
        headers=environment.authorization,
    )


async def test_ready_case_keeps_the_existing_detail_contract(
    trace_status: StatusEnvironment,
) -> None:
    """A readable Session still returns the full problem card."""
    response = await _detail(trace_status, "case-ready-m12-07")
    assert response.status_code == 200
    assert response.json()["badCaseId"] == "case-ready-m12-07"
    assert response.json()["sessionId"] == READY_SESSION


async def test_missing_case_remains_404(trace_status: StatusEnvironment) -> None:
    """A genuinely missing case keeps the original not-found semantics."""
    response = await _detail(trace_status, MISSING_CASE)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BAD_CASE_NOT_FOUND"


async def test_pending_and_syncing_return_409_with_structured_details(
    trace_status: StatusEnvironment,
) -> None:
    """Not-yet-synced and in-flight roots are pending, not missing."""
    for case_id, expected in (
        ("case-pending-m12-07", "pending"),
        ("case-pending-row-m12-07", "pending"),
        ("case-syncing-m12-07", "syncing"),
    ):
        response = await _detail(trace_status, case_id)
        assert response.status_code == 409, case_id
        error = response.json()["error"]
        assert error["code"] == "BAD_CASE_SESSION_PENDING"
        details = error["details"]
        assert details["syncStatus"] == expected
        assert details["sessionReady"] is False
        assert details["retryable"] is True
        assert details["lastError"] is None
        assert details["badCaseId"] == case_id
        assert details["title"] == f"Case {case_id}"


async def test_failed_and_unavailable_return_503_and_distinguish_retryability(
    trace_status: StatusEnvironment,
) -> None:
    """Transient failures retry automatically; deterministic ones do not."""
    failed = await _detail(trace_status, "case-failed-m12-07")
    assert failed.status_code == 503
    failed_error = failed.json()["error"]
    assert failed_error["code"] == "BAD_CASE_SESSION_UNAVAILABLE"
    failed_details = failed_error["details"]
    assert failed_details["syncStatus"] == "failed"
    assert failed_details["retryable"] is True
    assert failed_details["lastError"] == "SESSION_QUERY_TIMEOUT"
    assert failed_details["nextRetryAt"] is not None

    unavailable = await _detail(trace_status, "case-unavailable-m12-07")
    assert unavailable.status_code == 503
    unavailable_error = unavailable.json()["error"]
    assert unavailable_error["code"] == "BAD_CASE_SESSION_UNAVAILABLE"
    unavailable_details = unavailable_error["details"]
    assert unavailable_details["syncStatus"] == "unavailable"
    assert unavailable_details["retryable"] is False
    assert unavailable_details["lastError"] == "SESSION_QUERY_UNAVAILABLE"
    assert unavailable_details["nextRetryAt"] is None

    synced_lost = await _detail(trace_status, "case-synced-lost-m12-07")
    assert synced_lost.status_code == 503
    synced_details = synced_lost.json()["error"]["details"]
    assert synced_details["syncStatus"] == "unavailable"
    assert synced_details["retryable"] is False
    assert synced_details["lastError"] is None


async def test_ownership_mismatch_still_wins_over_trace_state(
    trace_status: StatusEnvironment,
) -> None:
    """A case from another Session is a 409 conflict, not a trace state."""
    response = await trace_status.client.get(
        f"/api/bad-cases/case-unavailable-m12-07?sessionId={OTHER_SESSION}",
        headers=trace_status.authorization,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BAD_CASE_SESSION_MISMATCH"


async def test_overview_list_exposes_the_five_trace_states(
    trace_status: StatusEnvironment,
) -> None:
    """The list carries sync status and retryability without a per-row read."""
    response = await trace_status.client.get(
        f"/api/workspaces/{DEFAULT_WORKSPACE_ID}/bad-cases",
        headers=trace_status.authorization,
        params={"pageSize": 50},
    )
    assert response.status_code == 200
    items = {item["badCaseId"]: item for item in response.json()["items"]}
    assert items["case-ready-m12-07"]["syncStatus"] == "ready"
    assert items["case-ready-m12-07"]["sessionReady"] is True
    assert items["case-pending-m12-07"]["syncStatus"] == "pending"
    assert items["case-pending-row-m12-07"]["syncStatus"] == "pending"
    assert items["case-syncing-m12-07"]["syncStatus"] == "syncing"
    assert items["case-failed-m12-07"]["syncStatus"] == "failed"
    assert items["case-failed-m12-07"]["retryable"] is True
    assert items["case-unavailable-m12-07"]["syncStatus"] == "unavailable"
    assert items["case-unavailable-m12-07"]["retryable"] is False
    assert items["case-unavailable-m12-07"]["lastError"] == "SESSION_QUERY_UNAVAILABLE"
    assert items["case-synced-lost-m12-07"]["syncStatus"] == "unavailable"
    assert items["case-synced-lost-m12-07"]["sessionReady"] is False


async def test_deterministic_failures_stop_retrying_and_can_be_rearmed(
    trace_status: StatusEnvironment,
) -> None:
    """The scheduler skips parked roots; a restart re-arms them once."""
    repository = BadCaseRootSyncRepository(trace_status.database)
    candidates = await repository.list_candidates(now_shanghai(), limit=100)
    assert FAILED_ROOT in candidates
    assert UNAVAILABLE_ROOT not in candidates

    rearmed = await repository.reset_deterministic_failures()
    assert rearmed >= 1
    state = await repository.get(UNAVAILABLE_ROOT)
    assert state is not None
    assert state.status == "pending"
    assert state.last_error is None
    assert state.source_snapshot is None
    assert UNAVAILABLE_ROOT in await repository.list_candidates(
        now_shanghai(),
        limit=100,
    )
    async with trace_status.database.transaction() as session:
        await session.execute(
            update(bad_case_root_sync)
            .where(bad_case_root_sync.c.root_session_id == UNAVAILABLE_ROOT)
            .values(status="failed", last_error="SESSION_QUERY_UNAVAILABLE"),
        )
    assert UNAVAILABLE_ROOT not in await repository.list_candidates(
        now_shanghai(),
        limit=100,
    )
    async with trace_status.database.session() as session:
        row: object = (
            await session.execute(
                select(bad_case_root_sync.c.status).where(
                    bad_case_root_sync.c.root_session_id == UNAVAILABLE_ROOT,
                ),
            )
        ).scalar_one()
    assert row == "failed"


def test_no_source_marks_every_unready_state_non_retryable() -> None:
    """Without a global or report source nothing can progress automatically."""
    now = now_shanghai()
    row = BadCaseRootSyncRow(
        root_session_id="root-m12-07",
        status="failed",
        source_kind="global",
        source_snapshot={"kind": "global"},
        attempts=1,
        last_error="SESSION_QUERY_TIMEOUT",
        agent_count=0,
        started_at=now,
        synced_at=None,
        next_retry_at=None,
        lease_owner=None,
        lease_expires_at=None,
        updated_at=now,
    )
    failed = classify_trace_status(row, session_ready=False, source_available=False)
    assert failed.status == "failed"
    assert failed.retryable is False

    pending = classify_trace_status(None, session_ready=False, source_available=False)
    assert pending.status == "pending"
    assert pending.retryable is False

    with_source = classify_trace_status(row, session_ready=False, source_available=True)
    assert with_source.retryable is True


async def test_reports_with_a_source_rearm_a_parked_root(
    trace_status: StatusEnvironment,
) -> None:
    """A fresh sessionSource turns a deterministic source failure back into pending."""
    repository = BadCaseRootSyncRepository(trace_status.database)
    async with trace_status.database.transaction() as session:
        rearmed = await insert_pending_root(
            session,
            UNAVAILABLE_ROOT,
            now=now_shanghai(),
            rearm_from_source=True,
        )
    assert rearmed is True
    state = await repository.get(UNAVAILABLE_ROOT)
    assert state is not None
    assert state.status == "pending"
    assert state.last_error is None
    assert state.source_snapshot is None


async def test_startup_recovers_a_synced_root_whose_session_disappeared(
    trace_status: StatusEnvironment,
) -> None:
    """A synced root without a normalized Session gets one fresh claim."""
    repository = BadCaseRootSyncRepository(trace_status.database)
    rearmed = await repository.rearm_missing_sessions()
    assert rearmed >= 1
    state = await repository.get(SYNCED_LOST_ROOT)
    assert state is not None
    assert state.status == "pending"
    ready = await repository.get(READY_SESSION)
    assert ready is not None
    assert ready.status == "synced"
