"""ClaudeUpstream source: endpoint delegation, envelope synthesis, and parity."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.service.acquisition.bad_case_sync import _payload_from_info
from app.service.acquisition.local_sessions import LocalAgentPayload
from app.third_party_api.bad_case_query.http import HttpBadCaseCatalogSource
from app.third_party_api.bad_case_sync_source.claude_upstream import (
    ClaudeUpstreamBadCaseSyncSource,
)
from app.third_party_api.session_query.http import HttpSessionQuerySource
from app.third_party_api.session_query.models import SessionTrajectory
from app.third_party_api.session_source import SessionSourceSnapshot
from app.utils.time import now_shanghai

ROOT = "root-session-1"
CHILD = "agent-child-1"
TRAJECTORY = json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n"
SNAPSHOT = SessionSourceSnapshot(kind="global", provider="claude-upstream")


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/children"):
        return httpx.Response(200, json=[CHILD])
    if request.url.path.endswith("/trajectory"):
        return httpx.Response(200, content=TRAJECTORY.encode("utf-8"))
    if request.url.path.endswith("/bad-cases"):
        return httpx.Response(
            200,
            json={
                "total": 1,
                "offset": 0,
                "limit": 10,
                "items": [
                    {
                        "bad_case_id": 1,
                        "bad_case_session_id": ROOT,
                        "bad_case_type": "self",
                        "object_name": "deep-research",
                        "object_type": "skill",
                        "object_version": "v1",
                        "bad_case_agent_id": None,
                        "trigger_line": None,
                        "bad_case_title": "case",
                        "bad_case_description": "description",
                        "meta_data": None,
                        "source": "test",
                        "created_at": "2026-11-24T10:00:00+08:00",
                        "updated_at": "2026-11-24T10:00:00+08:00",
                    },
                ],
            },
        )
    return httpx.Response(404)


def _source() -> tuple[
    ClaudeUpstreamBadCaseSyncSource,
    httpx.AsyncClient,
    httpx.AsyncClient,
]:
    session_client = httpx.AsyncClient(
        base_url="http://upstream.test",
        transport=httpx.MockTransport(_handler),
    )
    catalog_client = httpx.AsyncClient(
        base_url="http://upstream.test",
        transport=httpx.MockTransport(_handler),
    )
    source = ClaudeUpstreamBadCaseSyncSource(
        catalog=HttpBadCaseCatalogSource(catalog_client),
        session=HttpSessionQuerySource(session_client),
    )
    return source, session_client, catalog_client


def _settings(**overrides: Any) -> Settings:
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=Path("."),
        jwt_secret=SecretStr("claude-upstream-test-secret"),
        **cast(Any, overrides),
    )


@pytest.mark.asyncio
async def test_fetch_bad_case_page_goes_through_the_parent_template() -> None:
    """The service-facing template delegates to the subclass endpoint."""
    source, _, _ = _source()
    try:
        page = await source.fetch_bad_case_page(after_id=0, offset=0, limit=10)
    finally:
        await source.close()

    assert [item.bad_case_id for item in page.items] == [1]


@pytest.mark.asyncio
async def test_fetch_session_synthesizes_main_and_subagent_envelopes() -> None:
    """Projection reuses the registered adapter for both agent kinds."""
    source, _, _ = _source()
    try:
        main = await source.fetch_session(
            session_id=ROOT,
            expected_parent_id=None,
            snapshot=SNAPSHOT,
        )
        child = await source.fetch_session(
            session_id=CHILD,
            expected_parent_id=ROOT,
            snapshot=SNAPSHOT,
        )
    finally:
        await source.close()

    assert main.runtime_key == "claude-code"
    assert main.agent_kind == "main"
    assert main.parent_agent_id is None
    assert main.agent_meta is None
    assert main.child_session_ids == (CHILD,)
    assert main.trajectory.line_count == 1

    assert child.agent_kind == "subagent"
    assert child.parent_agent_id == ROOT
    assert child.agent_meta == {"parentAgentId": ROOT}


@pytest.mark.asyncio
async def test_close_releases_both_owned_clients() -> None:
    """One lifecycle call closes the catalog and session clients together."""
    source, session_client, catalog_client = _source()

    await source.close()

    assert session_client.is_closed is True
    assert catalog_client.is_closed is True


def test_from_settings_requires_both_endpoint_groups() -> None:
    """A selected provider without credentials fails composition."""
    with pytest.raises(ValueError, match="HE_SESSION_QUERY"):
        ClaudeUpstreamBadCaseSyncSource.from_settings(
            _settings(bad_case_sync_provider="claude-upstream"),
        )


@pytest.mark.asyncio
async def test_from_settings_builds_the_provider() -> None:
    """A fully configured deployment gets a usable source instance."""
    settings = _settings(
        bad_case_sync_provider="claude-upstream",
        session_query_base_url="http://session.test",
        session_query_token=SecretStr("session-token"),
        bad_case_query_base_url="http://catalog.test",
        bad_case_query_token=SecretStr("catalog-token"),
    )
    source = ClaudeUpstreamBadCaseSyncSource.from_settings(settings)
    try:
        assert isinstance(source, ClaudeUpstreamBadCaseSyncSource)
        assert source.provider == "claude-upstream"
    finally:
        await source.close()


@dataclass(frozen=True, slots=True)
class _OldPayload:
    """Reference implementation of the deleted ``_payload`` helper."""

    root_session_id: str
    agent_id: str
    agent_kind: str
    content: str
    content_hash: str
    line_count: int
    agent_meta: dict[str, object] | None
    source_updated_at: datetime
    discovered_at: datetime
    runtime_key: str = "claude-code"


def _old_payload(
    *,
    root_session_id: str,
    session_id: str,
    parent_id: str | None,
    trajectory: SessionTrajectory,
    now: datetime,
) -> _OldPayload:
    import hashlib

    encoded = trajectory.content.encode("utf-8")
    return _OldPayload(
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_id", "parent_id", "agent_kind", "agent_meta"),
    [
        pytest.param(ROOT, None, "main", None, id="main"),
        pytest.param(CHILD, ROOT, "subagent", {"parentAgentId": ROOT}, id="subagent"),
    ],
)
async def test_payload_projection_matches_the_removed_helper(
    session_id: str,
    parent_id: str | None,
    agent_kind: str,
    agent_meta: dict[str, object] | None,
) -> None:
    """The envelope projection keeps every payload field identical."""
    source, _, _ = _source()
    now = now_shanghai()
    try:
        info = await source.fetch_session(
            session_id=session_id,
            expected_parent_id=parent_id,
            snapshot=SNAPSHOT,
        )
    finally:
        await source.close()
    new = _payload_from_info(
        root_session_id=ROOT,
        session_id=session_id,
        info=info,
        now=now,
    )
    old = _old_payload(
        root_session_id=ROOT,
        session_id=session_id,
        parent_id=parent_id,
        trajectory=info.trajectory,
        now=now,
    )

    expected = asdict(old)
    actual: dict[str, Any] = asdict(new)
    assert new.agent_kind == agent_kind
    assert new.agent_meta == agent_meta
    assert actual == expected
    assert isinstance(new, LocalAgentPayload)
    assert new.runtime_key == "claude-code"
