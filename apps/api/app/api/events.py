"""HTTP adapter for one-time Server-Sent Events tickets."""

import re

from fastapi import APIRouter, Request, Security

from app.api.auth import identity_from
from app.api.security import BEARER_AUTH
from app.errors import AppError, ErrorCode, ErrorResponse
from app.service.identity.schemas import EventTicketResponse, TicketRequest

router = APIRouter(prefix="/api/events", tags=["events"])
_RUN_TOPIC = re.compile(r"^run:[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


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
