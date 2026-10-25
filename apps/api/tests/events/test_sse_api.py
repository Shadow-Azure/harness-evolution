"""SSE ticket endpoint and public OpenAPI behavior."""

from pathlib import Path
from typing import ClassVar

import httpx
from fastapi import Response
from pytest import MonkeyPatch

from app.api import events as events_api
from app.config import DatabaseDialect, Settings
from app.errors import AppError, ErrorCode
from app.main import create_app


async def test_event_stream_rejects_unknown_and_replayed_tickets(tmp_path: Path) -> None:
    """The streaming endpoint consumes signed grants exactly once."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    app = create_app(settings)
    token = app.state.identity.tickets.issue(
        user_id="user-1",
        topics=("run:r1",),
        last_event_id=0,
    )
    app.state.identity.tickets.consume(token)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        unknown = await client.get("/api/events?ticket=not-a-ticket")
        replayed = await client.get(f"/api/events?ticket={token}")

    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "TICKET_INVALID"
    assert replayed.status_code == 401
    assert replayed.json()["error"]["code"] == "TICKET_INVALID"


async def test_event_stream_missing_ticket_uses_stable_unauthorized_error(
    tmp_path: Path,
) -> None:
    """An absent SSE grant is invalid authorization, not request validation."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        response = await client.get("/api/events")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TICKET_INVALID"


async def test_ticket_issue_uses_injected_run_topic_authorizer(tmp_path: Path) -> None:
    """Resource authorization is an injectable seam owned by the evolution phase."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    app = create_app(settings)

    class DenyMissingRun:
        """Reject the example run while recording the authorization request."""

        calls: ClassVar[list[tuple[tuple[str, ...], str]]] = []

        async def authorize(self, topics: tuple[str, ...], *, user_id: str) -> None:
            """Require the run resource to exist in a future owning repository."""
            self.calls.append((topics, user_id))
            if topics == ("run:missing",):
                raise AppError(
                    status_code=401,
                    code=ErrorCode.TICKET_INVALID,
                    message="run topic is not available",
                )

    authorizer = DenyMissingRun()
    app.state.run_topic_authorizer = authorizer
    access_token = app.state.identity.tokens.create_access_token(
        user_id="user-1",
        role="member",
        must_change_password=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        response = await client.post(
            "/api/events/ticket",
            json={"topics": ["run:missing"], "lastEventId": 0},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TICKET_INVALID"
    assert authorizer.calls == [(("run:missing",), "user-1")]


async def test_ticket_issue_rejects_multiple_topics(tmp_path: Path) -> None:
    """M1 uses one integer cursor and therefore accepts exactly one run topic."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    app = create_app(settings)
    access_token = app.state.identity.tokens.create_access_token(
        user_id="user-1",
        role="member",
        must_change_password=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        response = await client.post(
            "/api/events/ticket",
            json={"topics": ["run:a", "run:b"], "lastEventId": 0},
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_INVALID"


async def test_event_stream_rejects_url_topics(tmp_path: Path) -> None:
    """Topics are authorized only inside the signed ticket."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    app = create_app(settings)
    token = app.state.identity.tickets.issue(
        user_id="user-1",
        topics=("run:r1",),
        last_event_id=0,
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        response = await client.get(
            f"/api/events?ticket={token}&topics=run:attacker",
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TICKET_INVALID"


async def test_event_stream_rejects_invalid_last_event_id(tmp_path: Path) -> None:
    """A malformed browser reconnect cursor fails before a stream is opened."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    app = create_app(settings)
    token = app.state.identity.tickets.issue(
        user_id="user-1",
        topics=("run:r1",),
        last_event_id=0,
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        response = await client.get(
            f"/api/events?ticket={token}",
            headers={"Last-Event-ID": "-1"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_INVALID"
    assert app.state.identity.tickets.active_count == 1


def test_openapi_documents_jobs_and_ticket_stream_without_bearer() -> None:
    """Jobs use Bearer while the EventSource endpoint authorizes via its query ticket."""
    app = create_app(Settings(db_dialect=DatabaseDialect.SQLITE))
    schema = app.openapi()

    assert "/api/jobs/{jobId}" in schema["paths"]
    assert "/api/events" in schema["paths"]
    assert schema["paths"]["/api/jobs/{jobId}"]["get"]["security"] == [{"BearerAuth": []}]
    assert schema["paths"]["/api/jobs/{jobId}"]["get"]["parameters"][0]["name"] == "jobId"
    assert "security" not in schema["paths"]["/api/events"]["get"]
    event_response = schema["paths"]["/api/events"]["get"]["responses"]["200"]
    assert set(event_response["content"]) == {"text/event-stream"}
    event_schema = event_response["content"]["text/event-stream"]["schema"]
    assert set(event_schema["required"]) == {"event", "data"}
    assert "ping" in event_schema["properties"]["event"]["enum"]
    assert "reset" in event_schema["properties"]["event"]["enum"]
    components = schema["components"]["schemas"]
    assert {"JobResponse", "EventTicketResponse"} <= set(components)
    assert schema["components"]["schemas"]["ErrorCode"]["enum"]
    assert "JOB_NOT_FOUND" in schema["components"]["schemas"]["ErrorCode"]["enum"]
    assert "RUN_BUSY" in schema["components"]["schemas"]["ErrorCode"]["enum"]
    ticket_request = schema["components"]["schemas"]["TicketRequest"]
    assert ticket_request["properties"]["topics"]["maxItems"] == 1


async def test_event_stream_disables_library_keepalive_ping(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Only the application's configurable named ping remains active."""
    settings = Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path)
    app = create_app(settings)
    token = app.state.identity.tickets.issue(
        user_id="user-1",
        topics=("run:r1",),
        last_event_id=0,
    )
    captured: dict[str, object] = {}

    def capture_response(content: object, **kwargs: object) -> Response:
        captured["content"] = content
        captured.update(kwargs)
        return Response(media_type="text/event-stream")

    monkeypatch.setattr(events_api, "EventSourceResponse", capture_response)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        response = await client.get(f"/api/events?ticket={token}")

    assert response.status_code == 200
    assert captured["ping"] == 0
