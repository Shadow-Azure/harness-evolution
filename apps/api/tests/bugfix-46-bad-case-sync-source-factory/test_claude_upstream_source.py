"""Claude-upstream source: settings wiring, delegation, envelope, projection."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.third_party_api.bad_case_query.http import HttpBadCaseCatalogSource
from app.third_party_api.bad_case_sync_source import (
    ClaudeUpstreamBadCaseSyncSource,
    ClaudeUpstreamEnvelopeFactory,
)
from app.third_party_api.session_query.http import HttpSessionQuerySource
from app.third_party_api.session_query.models import SessionTrajectory
from app.third_party_api.session_source.base import SessionSourceSnapshot

ROOT = "root-session-1"
CHILD = "agent-child-1"
TRAJECTORY_BODY = "\n".join(
    [
        json.dumps({"type": "user", "message": {"content": "prompt"}}),
        json.dumps({"type": "assistant", "message": {"id": "m1"}}),
    ],
)
"""Two NDJSON objects; the client canonicalizes them into two compact lines."""

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def _catalog_item() -> dict[str, Any]:
    """Return one upstream bad case that satisfies the strict page contract."""
    return {
        "bad_case_id": 11,
        "bad_case_session_id": ROOT,
        "bad_case_type": "self",
        "bad_case_title": "case title",
        "bad_case_description": "case description",
    }


def _handler() -> Handler:
    """Serve both upstream endpoints from one deterministic transport."""

    async def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/bad-cases":
            return httpx.Response(
                200,
                json={"total": 1, "offset": 0, "limit": 1, "items": [_catalog_item()]},
            )
        if path == f"/sessions/{ROOT}/children":
            return httpx.Response(200, json=[CHILD])
        if path == f"/sessions/{CHILD}/children":
            return httpx.Response(200, json=[])
        if path in {f"/sessions/{ROOT}/trajectory", f"/sessions/{CHILD}/trajectory"}:
            return httpx.Response(
                200,
                text=TRAJECTORY_BODY,
                headers={"content-type": "application/x-ndjson"},
            )
        raise AssertionError(f"unexpected path: {path}")

    return handle


def _source(handler: Handler) -> ClaudeUpstreamBadCaseSyncSource:
    """Build one source over mock transports, skipping client construction."""
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return ClaudeUpstreamBadCaseSyncSource(
        HttpBadCaseCatalogSource(
            httpx.AsyncClient(base_url="http://catalog.test", transport=transport),
            max_retries=0,
        ),
        HttpSessionQuerySource(
            httpx.AsyncClient(base_url="http://session.test", transport=transport),
            max_retries=0,
        ),
    )


def _trajectory() -> SessionTrajectory:
    """Return one canonical trajectory reused by the envelope assertions."""
    return SessionTrajectory(content=TRAJECTORY_BODY, line_count=2)


def _snapshot() -> SessionSourceSnapshot:
    """Return today's frozen global snapshot (provider arrives in the next step)."""
    return SessionSourceSnapshot(kind="global")


@pytest.mark.asyncio
async def test_fetch_bad_case_page_returns_the_validated_catalog_page() -> None:
    """The parent template delegates one page to the catalog client unchanged."""
    source = _source(_handler())
    try:
        page = await source.fetch_bad_case_page(after_id=10, offset=0, limit=1)
    finally:
        await source.close()

    assert page.items[0].bad_case_id == 11
    assert page.items[0].title == "case title"


@pytest.mark.asyncio
async def test_fetch_session_projects_a_main_agent_through_the_parent_template() -> None:
    """A root session becomes a main-agent SessionInfo with no agent metadata."""
    source = _source(_handler())
    try:
        info = await source.fetch_session(
            session_id=ROOT,
            expected_parent_id=None,
            snapshot=_snapshot(),
        )
    finally:
        await source.close()

    assert info.runtime_key == "claude-code"
    assert info.agent_kind == "main"
    assert info.parent_agent_id is None
    assert info.agent_meta is None
    assert info.child_session_ids == (CHILD,)
    assert info.trajectory.line_count == 2


@pytest.mark.asyncio
async def test_fetch_session_projects_a_subagent_with_its_parent_metadata() -> None:
    """A child session becomes a subagent SessionInfo carrying parentAgentId."""
    source = _source(_handler())
    try:
        info = await source.fetch_session(
            session_id=CHILD,
            expected_parent_id=ROOT,
            snapshot=_snapshot(),
        )
    finally:
        await source.close()

    assert info.runtime_key == "claude-code"
    assert info.agent_kind == "subagent"
    assert info.parent_agent_id == ROOT
    assert info.agent_meta == {"parentAgentId": ROOT}
    assert info.child_session_ids == ()


def test_build_envelope_matches_the_documented_main_agent_json() -> None:
    """The synthesized envelope is exactly the §6 Step 6c shape for a main agent."""
    source = _source(_handler())
    envelope = source.build_envelope(
        session_id=ROOT,
        expected_parent_id=None,
        children=(CHILD,),
        trajectory=_trajectory(),
    )

    assert envelope.model_dump(by_alias=True) == {
        "schemaVersion": 1,
        "sessionId": ROOT,
        "runtime": "claude-code",
        "runtimeVersion": None,
        "agentKind": "main",
        "parentSessionId": None,
        "childSessionIds": [CHILD],
        "agentMeta": {},
        "trajectory": {
            "format": "ndjson",
            "lineCount": 2,
            "content": TRAJECTORY_BODY,
        },
        "updatedAt": None,
    }


def test_build_envelope_marks_a_child_session_as_a_subagent() -> None:
    """The traversal parent, not the session id shape, decides the agent kind."""
    envelope = ClaudeUpstreamEnvelopeFactory.build(
        runtime_key="claude-code",
        session_id=CHILD,
        expected_parent_id=ROOT,
        children=(),
        trajectory=_trajectory(),
    )

    assert envelope.agent_kind == "subagent"
    assert envelope.parent_session_id == ROOT
    assert envelope.agent_meta == {}
    assert envelope.child_session_ids == []
    assert envelope.trajectory.line_count == 2


class _FakeClient:
    """Record one ``httpx.AsyncClient`` construction and its close call."""

    instances: ClassVar[list[_FakeClient]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        _FakeClient.instances.append(self)

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_from_settings_builds_two_clients_and_close_releases_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both clients carry their endpoint, Bearer token, timeout, and no redirects."""
    _FakeClient.instances.clear()
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    settings = Settings(
        jwt_secret=SecretStr("bad-case-sync-source-test-secret"),
        session_query_base_url="http://session.test",
        session_query_token=SecretStr("session-token"),
        session_query_timeout_seconds=45.0,
        session_query_retry_attempts=4,
        session_query_retry_backoff_seconds=1.5,
        bad_case_query_base_url="http://catalog.test",
        bad_case_query_token=SecretStr("catalog-token"),
        bad_case_query_timeout_seconds=30.0,
        bad_case_query_retry_attempts=3,
        bad_case_query_retry_backoff_seconds=2.5,
    )

    source = ClaudeUpstreamBadCaseSyncSource.from_settings(settings)
    session_client, catalog_client = _FakeClient.instances

    assert session_client.kwargs == {
        "base_url": "http://session.test",
        "headers": {"Authorization": "Bearer session-token"},
        "timeout": 45.0,
        "follow_redirects": False,
    }
    assert catalog_client.kwargs == {
        "base_url": "http://catalog.test",
        "headers": {"Authorization": "Bearer catalog-token"},
        "timeout": 30.0,
        "follow_redirects": False,
    }
    assert isinstance(source._catalog, HttpBadCaseCatalogSource)
    assert isinstance(source._session, HttpSessionQuerySource)
    assert source._catalog._max_retries == 3
    assert source._catalog._backoff_seconds == 2.5
    assert source._session._max_retries == 4
    assert source._session._backoff_seconds == 1.5

    await source.close()

    assert session_client.closed is True
    assert catalog_client.closed is True


@pytest.mark.asyncio
async def test_close_releases_the_session_client_when_the_catalog_close_fails() -> None:
    """A failing first close must not leak the second client."""
    closed: list[str] = []

    class CatalogClient:
        async def aclose(self) -> None:
            raise RuntimeError("catalog close failed")

    class SessionClient:
        async def aclose(self) -> None:
            closed.append("session")

    source = ClaudeUpstreamBadCaseSyncSource(
        HttpBadCaseCatalogSource(CatalogClient()),  # type: ignore[arg-type]
        HttpSessionQuerySource(SessionClient()),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="catalog close failed"):
        await source.close()

    assert closed == ["session"]
