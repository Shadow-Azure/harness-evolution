"""Global session path: deleted-projection parity, snapshot rules, provider freeze."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import SecretStr, ValidationError

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_sync import BadCaseRootSyncRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.service.acquisition.bad_case_sync import (
    BadCaseRootSyncService,
    _payload_from_info,
)
from app.service.acquisition.local_sessions import LocalAgentPayload
from app.third_party_api.bad_case_query.models import BadCasePage
from app.third_party_api.bad_case_sync_source import (
    BaseBadCaseSyncSource,
    ClaudeUpstreamEnvelopeFactory,
)
from app.third_party_api.session_query.models import SessionTrajectory
from app.third_party_api.session_source.base import (
    SessionSourceEnvelope,
    SessionSourceSnapshot,
)
from app.utils.time import now_shanghai

ROOT = "root-session-1"
CHILD = "agent-child-1"
TRAJECTORY_CONTENT = "\n".join(
    [
        '{"type": "user", "message": {"content": "prompt"}}',
        '{"type": "assistant", "message": {"id": "m1"}}',
    ],
)
PAYLOAD_FIELDS = (
    "root_session_id",
    "agent_id",
    "agent_kind",
    "content",
    "content_hash",
    "line_count",
    "agent_meta",
    "source_updated_at",
    "discovered_at",
    "runtime_key",
)


def _trajectory() -> SessionTrajectory:
    """Return one deterministic canonical trajectory for both projections."""
    return SessionTrajectory(content=TRAJECTORY_CONTENT, line_count=2)


def _legacy_payload(
    *,
    root_session_id: str,
    session_id: str,
    parent_id: str | None,
    trajectory: SessionTrajectory,
    now: datetime,
) -> LocalAgentPayload:
    """Reference implementation of the deleted ``_payload()`` (main @ 2f4bce1d)."""
    encoded = trajectory.content.encode("utf-8")
    return LocalAgentPayload(
        root_session_id=root_session_id,
        agent_id=session_id,
        agent_kind="main" if session_id == root_session_id else "subagent",
        content=trajectory.content,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        line_count=trajectory.line_count,
        agent_meta=None if session_id == root_session_id else {"parentAgentId": parent_id},
        source_updated_at=now,
        discovered_at=now,
    )


def _assert_payload_matches(actual: LocalAgentPayload, expected: LocalAgentPayload) -> None:
    """Compare the parity fields one by one so a mismatch names its field."""
    for field in PAYLOAD_FIELDS:
        assert getattr(actual, field) == getattr(expected, field), field


class FakeSource(BaseBadCaseSyncSource):
    """Parent-template source whose envelope synthesis matches the Claude upstream."""

    provider = "claude-upstream"

    @classmethod
    def from_settings(cls, settings: Settings) -> FakeSource:
        raise NotImplementedError("the contract fake is constructed directly")

    async def fetch_page(
        self,
        *,
        after_id: int,
        offset: int,
        limit: int,
    ) -> BadCasePage:
        raise NotImplementedError("the contract fake never reads catalog pages")

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        return _trajectory()

    async def list_children(self, session_id: str) -> tuple[str, ...]:
        return (CHILD,) if session_id == ROOT else ()

    def build_envelope(
        self,
        *,
        session_id: str,
        expected_parent_id: str | None,
        children: tuple[str, ...],
        trajectory: SessionTrajectory,
    ) -> SessionSourceEnvelope:
        return ClaudeUpstreamEnvelopeFactory.build(
            runtime_key="claude-code",
            session_id=session_id,
            expected_parent_id=expected_parent_id,
            children=children,
            trajectory=trajectory,
        )

    async def close(self) -> None:
        return None


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide one migrated SQLite database isolated per test."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("global-session-contract-secret"),
    )
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


def _service(database: Database, source: BaseBadCaseSyncSource | None) -> BadCaseRootSyncService:
    """Build the root-sync service over the given global source."""
    return BadCaseRootSyncService(
        database,
        BadCaseRootSyncRepository(database),
        source,
        batch_size=10,
        time_budget_seconds=60,
        max_agents=10,
        max_depth=5,
        lease_seconds=60,
    )


@pytest.mark.asyncio
async def test_main_agent_payload_matches_the_deleted_projection() -> None:
    """The main-agent SessionInfo projects to exactly the old ``_payload()`` fields."""
    source = FakeSource()
    now = now_shanghai()
    try:
        info = await source.fetch_session(
            session_id=ROOT,
            expected_parent_id=None,
            snapshot=SessionSourceSnapshot(kind="global"),
        )
    finally:
        await source.close()

    actual = _payload_from_info(
        root_session_id=ROOT,
        session_id=ROOT,
        info=info,
        now=now,
    )
    expected = _legacy_payload(
        root_session_id=ROOT,
        session_id=ROOT,
        parent_id=None,
        trajectory=info.trajectory,
        now=now,
    )

    _assert_payload_matches(actual, expected)
    assert actual.agent_kind == "main"
    assert actual.agent_meta is None
    assert actual.runtime_key == "claude-code"


@pytest.mark.asyncio
async def test_subagent_payload_matches_the_deleted_projection() -> None:
    """A child SessionInfo keeps the old subagent kind, parent meta, and runtime."""
    source = FakeSource()
    now = now_shanghai()
    try:
        info = await source.fetch_session(
            session_id=CHILD,
            expected_parent_id=ROOT,
            snapshot=SessionSourceSnapshot(kind="global"),
        )
    finally:
        await source.close()

    actual = _payload_from_info(
        root_session_id=ROOT,
        session_id=CHILD,
        info=info,
        now=now,
    )
    expected = _legacy_payload(
        root_session_id=ROOT,
        session_id=CHILD,
        parent_id=ROOT,
        trajectory=info.trajectory,
        now=now,
    )

    _assert_payload_matches(actual, expected)
    assert actual.agent_kind == "subagent"
    assert actual.agent_meta == {"parentAgentId": ROOT}
    assert actual.runtime_key == "claude-code"


def test_report_snapshot_rejects_a_provider() -> None:
    """A report snapshot may never carry the global line's provider."""
    with pytest.raises(ValidationError, match="cannot carry a provider"):
        SessionSourceSnapshot(
            kind="report",
            session_url_template="https://trace.test/api/sessions/{sessionId}",
            provider="claude-upstream",
        )


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param(
            {"session_url_template": "https://trace.test/api/sessions/{sessionId}"},
            id="template",
        ),
        pytest.param({"runtime": "claude-code"}, id="runtime"),
    ],
)
def test_global_snapshot_rejects_report_fields(extra: dict[str, str]) -> None:
    """A global snapshot may never carry a report template or runtime."""
    with pytest.raises(ValidationError, match="cannot carry report fields"):
        SessionSourceSnapshot.model_validate({"kind": "global", **extra})


def test_bare_global_snapshot_is_still_valid() -> None:
    """The snapshots frozen before the provider field existed still validate."""
    snapshot = SessionSourceSnapshot.model_validate({"kind": "global"})

    assert snapshot.provider is None
    assert snapshot.runtime is None
    assert snapshot.session_url_template is None


def test_global_snapshot_accepts_a_frozen_provider() -> None:
    """A global snapshot may name the provider that fetched the root."""
    snapshot = SessionSourceSnapshot.model_validate(
        {"kind": "global", "provider": "claude-upstream"},
    )

    assert snapshot.provider == "claude-upstream"
    assert snapshot.runtime is None
    assert snapshot.session_url_template is None


@pytest.mark.asyncio
async def test_select_source_freezes_the_current_provider(database: Database) -> None:
    """The first claim records the assembled provider instead of a later .env value."""
    kind, snapshot = await _service(database, FakeSource())._select_source(ROOT)

    assert kind == "global"
    assert snapshot == {"kind": "global", "provider": "claude-upstream"}


@pytest.mark.asyncio
async def test_select_source_keeps_a_bare_global_snapshot_without_a_source(
    database: Database,
) -> None:
    """An unconfigured global line still freezes the legacy bare snapshot."""
    kind, snapshot = await _service(database, None)._select_source(ROOT)

    assert kind == "global"
    assert snapshot == {"kind": "global"}
