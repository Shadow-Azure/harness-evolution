"""HTTP adapter for one-time Server-Sent Events tickets."""

import json
import re
from collections.abc import AsyncGenerator
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Header, Query, Request, Security
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.api.auth import identity_from
from app.api.security import BEARER_AUTH
from app.errors import AppError, ErrorCode, ErrorResponse
from app.service.events import (
    EventBus,
    RunEventReplay,
    RunTopicAuthorizer,
    SSEEvent,
    stream_events,
)
from app.service.identity.schemas import EventTicketResponse, IdentityModel, TicketRequest

router = APIRouter(prefix="/api/events", tags=["events"])
_RUN_TOPIC = re.compile(r"^run:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SSEEventName = Literal[
    "ping",
    "run.event",
    "run.progress",
    "run.blocked",
    "run.resumed",
    "run.completed",
    "run.failed",
    "run.interrupted",
    "reset",
]


class SSEEventFrame(IdentityModel):
    """Logical Server-Sent Event frame documented for typed browser clients."""

    id: str | None = None
    event: SSEEventName
    data: dict[str, Any]


@router.post(
    "/ticket",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        401: {"model": ErrorResponse, "description": "Authentication or ticket input is invalid"},
        403: {"model": ErrorResponse, "description": "Password change is required"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
    },
)
async def issue_ticket(body: TicketRequest, request: Request) -> EventTicketResponse:
    """Bind authenticated run topics and a cursor to a single-use ticket."""
    if any(not _RUN_TOPIC.fullmatch(topic) for topic in body.topics):
        raise AppError(
            status_code=401,
            code=ErrorCode.TICKET_INVALID,
            message="event topics are invalid",
        )
    authorizer = cast(RunTopicAuthorizer, request.app.state.run_topic_authorizer)
    await authorizer.authorize(
        tuple(body.topics),
        user_id=request.state.principal.user_id,
    )
    ticket = identity_from(request).tickets.issue(
        user_id=request.state.principal.user_id,
        topics=tuple(body.topics),
        last_event_id=body.last_event_id,
    )
    return EventTicketResponse(
        ticket=ticket,
        expires_in=request.app.state.settings.event_ticket_ttl_seconds,
        topics=body.topics,
    )


def _parse_cursor(value: str | None) -> int:
    """Parse one non-negative replay cursor from the HTTP reconnect header."""
    if value is None or value == "":
        return 0
    try:
        cursor = int(value)
    except ValueError as exc:
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_INVALID,
            message="Last-Event-ID must be a non-negative integer",
        ) from exc
    if cursor < 0:
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_INVALID,
            message="Last-Event-ID must be a non-negative integer",
        )
    return cursor


async def _server_events(
    source: AsyncGenerator[SSEEvent, None],
) -> AsyncGenerator[ServerSentEvent, None]:
    """Serialize service events into the sse-starlette wire contract."""
    async for item in source:
        yield ServerSentEvent(
            event=item.event,
            data=json.dumps(item.data, ensure_ascii=False, separators=(",", ":")),
            id=str(item.event_id) if item.event_id is not None else None,
        )


@router.get(
    "",
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": "Server-Sent Event frames for authorized run topics",
            "content": {
                "text/event-stream": {
                    "schema": SSEEventFrame.model_json_schema(),
                },
            },
        },
        401: {"model": ErrorResponse, "description": "Event ticket is invalid or expired"},
        422: {"model": ErrorResponse, "description": "Replay cursor is invalid"},
    },
)
async def event_stream(
    request: Request,
    ticket: Annotated[str | None, Query()] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    topics: Annotated[str | None, Query(include_in_schema=False)] = None,
) -> EventSourceResponse:
    """Consume a one-time ticket and stream replay plus live run notifications."""
    if topics is not None:
        raise AppError(
            status_code=401,
            code=ErrorCode.TICKET_INVALID,
            message="event topics are authorized only by the ticket",
        )
    if not ticket:
        raise AppError(
            status_code=401,
            code=ErrorCode.TICKET_INVALID,
            message="event ticket is required",
        )
    header_cursor = _parse_cursor(last_event_id) if last_event_id is not None else None
    grant = identity_from(request).tickets.consume(ticket)
    settings = request.app.state.settings
    cursor = header_cursor if header_cursor is not None else grant.last_event_id
    source = stream_events(
        bus=cast(EventBus, request.app.state.event_bus),
        replay=cast(RunEventReplay, request.app.state.run_event_replay),
        topics=grant.topics,
        cursor=cursor,
        heartbeat_seconds=settings.sse_heartbeat_seconds,
        replay_limit=settings.event_replay_limit,
    )
    return EventSourceResponse(_server_events(source), ping=0)
