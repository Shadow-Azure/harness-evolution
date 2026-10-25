"""Storage primitives for idempotent root-level acquisition replay."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.db.base import Database
from app.db.models.domain import (
    agent_events,
    agents,
    session_families,
    source_records,
    sync_runs,
    trajectory_payloads,
    user_turns,
)
from app.service.acquisition.agent_tree import AssembledSessionTree
from app.utils.time import as_shanghai


@dataclass(frozen=True, slots=True)
class PendingPayload:
    """One raw payload whose processing cursor needs attention."""

    root_session_id: str
    agent_id: str
    agent_kind: str
    payload: str
    agent_meta: dict[str, object] | None
    content_hash: str
    line_count: int
    source_type: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RootPayload:
    """One current payload plus its durable processing cursor metadata."""

    root_session_id: str
    agent_id: str
    agent_kind: str
    payload: str
    agent_meta: dict[str, object] | None
    content_hash: str
    line_count: int
    source_type: str
    updated_at: datetime
    source_id: int | None
    received_at: datetime | None


def _payload_values(row: object) -> PendingPayload:
    """Project one joined payload row into a typed immutable value."""
    values = cast(dict[str, object], row)
    metadata = values["agent_meta"]
    return PendingPayload(
        root_session_id=str(values["root_session_id"]),
        agent_id=str(values["agent_id"]),
        agent_kind=str(values["agent_kind"]),
        payload=str(values["payload"]),
        agent_meta=cast(dict[str, object] | None, metadata),
        content_hash=str(values["content_hash"]),
        line_count=int(str(values["line_count"])),
        source_type=str(values["source_type"]),
        updated_at=as_shanghai(cast(datetime, values["updated_at"])),
    )


def _root_payload_values(row: object) -> RootPayload:
    """Project one payload and its optional source cursor."""
    values = cast(dict[str, object], row)
    payload = _payload_values(values)
    source_id = values.get("source_id")
    received_at = values.get("received_at")
    return RootPayload(
        root_session_id=payload.root_session_id,
        agent_id=payload.agent_id,
        agent_kind=payload.agent_kind,
        payload=payload.payload,
        agent_meta=payload.agent_meta,
        content_hash=payload.content_hash,
        line_count=payload.line_count,
        source_type=payload.source_type,
        updated_at=payload.updated_at,
        source_id=int(str(source_id)) if source_id is not None else None,
        received_at=(as_shanghai(cast(datetime, received_at)) if received_at is not None else None),
    )


def _joined_payload_query() -> Select[tuple[object, ...]]:
    """Select raw payload columns with optional processing cursor columns."""
    return select(
        trajectory_payloads.c.root_session_id,
        trajectory_payloads.c.agent_id,
        trajectory_payloads.c.agent_kind,
        trajectory_payloads.c.payload,
        trajectory_payloads.c.agent_meta,
        trajectory_payloads.c.content_hash,
        trajectory_payloads.c.line_count,
        trajectory_payloads.c.source_type,
        trajectory_payloads.c.updated_at,
        source_records.c.id.label("source_id"),
        source_records.c.received_at,
    ).select_from(
        trajectory_payloads.outerjoin(
            source_records,
            (source_records.c.root_session_id == trajectory_payloads.c.root_session_id)
            & (source_records.c.agent_id == trajectory_payloads.c.agent_id),
        ),
    )


async def list_pending_payloads(
    database: Database,
    parser_version: int,
) -> tuple[PendingPayload, ...]:
    """Return payloads without a current hash/parser processing cursor."""
    async with database.session() as session:
        rows = (
            (
                await session.execute(
                    _joined_payload_query()
                    .where(
                        or_(
                            source_records.c.id.is_(None),
                            source_records.c.processed_hash.is_(None),
                            source_records.c.processed_hash != trajectory_payloads.c.content_hash,
                            source_records.c.parser_version.is_(None),
                            source_records.c.parser_version < parser_version,
                        ),
                    )
                    .order_by(
                        trajectory_payloads.c.root_session_id,
                        trajectory_payloads.c.agent_id,
                    ),
                )
            )
            .mappings()
            .all()
        )
    return tuple(_payload_values(dict(row)) for row in rows)


async def list_root_payloads(
    database: Database,
    root_session_id: str,
) -> tuple[RootPayload, ...]:
    """Return every persisted payload for one root, independent of cursor state."""
    async with database.session() as session:
        rows = (
            (
                await session.execute(
                    _joined_payload_query()
                    .where(trajectory_payloads.c.root_session_id == root_session_id)
                    .order_by(trajectory_payloads.c.agent_id),
                )
            )
            .mappings()
            .all()
        )
    return tuple(_root_payload_values(dict(row)) for row in rows)


async def count_payloads(database: Database) -> int:
    """Return the number of current raw payload identities."""
    async with database.session() as session:
        value = (
            await session.execute(select(func.count()).select_from(trajectory_payloads))
        ).scalar_one()
    return int(value)


async def create_sync_run(
    database: Database,
    *,
    sync_run_id: str,
    source_type: str,
    started_at: datetime,
    records_total: int,
) -> None:
    """Create one running replay audit row."""
    async with database.transaction() as session:
        await session.execute(
            sync_runs.insert().values(
                id=sync_run_id,
                source_type=source_type,
                started_at=as_shanghai(started_at),
                finished_at=None,
                status="running",
                records_total=records_total,
                records_done=0,
                imported=0,
                skipped=0,
                errors=[],
            ),
        )


async def finish_sync_run(
    database: Database,
    *,
    sync_run_id: str,
    finished_at: datetime,
    records_done: int,
    imported: int,
    skipped: int,
    errors: list[dict[str, object]],
) -> None:
    """Finalize one replay audit row without hiding recoverable errors."""
    async with database.transaction() as session:
        await session.execute(
            sync_runs.update()
            .where(sync_runs.c.id == sync_run_id)
            .values(
                finished_at=as_shanghai(finished_at),
                status="completed",
                records_done=records_done,
                imported=imported,
                skipped=skipped,
                errors=errors,
            ),
        )


def _turn_id(root_session_id: str, seq: int) -> str:
    """Derive a stable public user-turn id from its root-local sequence."""
    digest = hashlib.sha256(f"{root_session_id}\0{seq}".encode()).hexdigest()[:31]
    return f"turn_{digest}"


def _json_value(value: object) -> object:
    """Thaw immutable provider metadata into a JSON-serializable value."""
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


async def _ensure_sources(
    session: AsyncSession,
    payloads: tuple[RootPayload, ...],
    *,
    discovered_at: datetime,
) -> dict[tuple[str, str], int]:
    """Create missing source cursors and return the complete identity map."""
    for payload in payloads:
        if payload.source_id is not None:
            continue
        await session.execute(
            source_records.insert().values(
                root_session_id=payload.root_session_id,
                agent_id=payload.agent_id,
                kind=payload.agent_kind,
                source_type=payload.source_type,
                line_count=payload.line_count,
                received_at=as_shanghai(discovered_at),
                processed_at=None,
                processed_hash=None,
                parser_version=None,
                last_sync_run_id=None,
            ),
        )
    rows = (
        await session.execute(
            select(
                source_records.c.id,
                source_records.c.root_session_id,
                source_records.c.agent_id,
            ).where(
                source_records.c.root_session_id == payloads[0].root_session_id,
            ),
        )
    ).all()
    return {(str(root), str(agent)): int(str(source_id)) for source_id, root, agent in rows}


async def _delete_root_tree(session: AsyncSession, root_session_id: str) -> None:
    """Delete one root in foreign-key-safe order."""
    root_agent_ids = select(agents.c.id).where(
        agents.c.root_session_id == root_session_id,
    )
    await session.execute(
        delete(agent_events).where(agent_events.c.agent_id.in_(root_agent_ids)),
    )
    await session.execute(delete(agents).where(agents.c.root_session_id == root_session_id))
    await session.execute(
        delete(user_turns).where(user_turns.c.root_session_id == root_session_id),
    )
    await session.execute(
        delete(session_families).where(session_families.c.id == root_session_id),
    )


async def replace_normalized_root(
    database: Database,
    *,
    tree: AssembledSessionTree,
    payloads: tuple[RootPayload, ...],
    parser_version: int,
    sync_run_id: str,
    completed_at: datetime,
) -> None:
    """Replace one root's canonical rows and advance all current source cursors."""
    if not payloads:
        raise ValueError("root payloads must not be empty")
    if tree.started_at is None or tree.ended_at is None:
        raise ValueError("assembled root must have session timestamps")
    started_at = tree.started_at
    ended_at = tree.ended_at
    async with database.transaction() as session:
        source_ids = await _ensure_sources(
            session,
            payloads,
            discovered_at=completed_at,
        )
        await _delete_root_tree(session, tree.id)
        source_rows = (
            (
                await session.execute(
                    select(source_records).where(source_records.c.root_session_id == tree.id),
                )
            )
            .mappings()
            .all()
        )
        imported_at = min(as_shanghai(cast(datetime, row["received_at"])) for row in source_rows)
        main_node = next(node for node in tree.nodes if node.kind == "main")
        source_type = next(
            payload.source_type for payload in payloads if payload.agent_id == main_node.id
        )
        await session.execute(
            session_families.insert().values(
                id=tree.id,
                short_title=tree.short_title,
                title=tree.title,
                search_text=tree.search_text,
                repo_name=tree.repo_name[:255],
                project_path=tree.root_metadata.cwd or "",
                git_branch=tree.root_metadata.git_branch,
                cli_version=tree.root_metadata.cli_version,
                entrypoint=tree.root_metadata.entrypoint,
                model=tree.model,
                models=list(tree.models),
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=max(
                    0,
                    int((ended_at - started_at).total_seconds()),
                ),
                status=tree.status,
                skill_names=list(tree.skill_names),
                user_turns_count=tree.user_turns_count,
                messages_count=tree.messages_count,
                tools_count=tree.tools_count,
                errors_count=tree.errors_count,
                agents_count=tree.agents_count,
                tokens_total=tree.tokens_total,
                source_type=source_type,
                main_record_id=source_ids[(tree.id, main_node.id)],
                imported_at=imported_at,
                updated_at=as_shanghai(completed_at),
            ),
        )
        for node in tree.nodes:
            await session.execute(
                agents.insert().values(
                    id=node.id,
                    root_session_id=tree.id,
                    parent_agent_id=node.parent_agent_id,
                    kind=node.kind,
                    agent_type=node.agent_type,
                    task_kind=node.task_kind,
                    team_name=node.team_name,
                    name=node.name,
                    skill_name=node.skill_name,
                    model=node.model,
                    requested_model=node.requested_model,
                    description=node.description,
                    tool_use_id=node.tool_use_id,
                    spawn_depth=node.spawn_depth,
                    transcript_record_id=source_ids.get((tree.id, node.id)),
                    lines=node.lines,
                    messages_count=node.messages_count,
                    tokens_total=node.tokens_total,
                    tools_count=node.tools_count,
                    errors_count=node.errors_count,
                    meta=_json_value(node.agent_meta),
                    sort_key=node.sort_key,
                ),
            )
        for node in tree.nodes:
            for event in node.events:
                await session.execute(
                    agent_events.insert().values(
                        agent_id=node.id,
                        event_index=event.event_index,
                        line_no=event.line_no,
                        message_offset=event.message_offset,
                        kind=event.kind,
                        name=event.name,
                        description=event.description,
                        tool_use_id=event.tool_use_id,
                    ),
                )
        for turn in tree.user_turns:
            await session.execute(
                user_turns.insert().values(
                    id=_turn_id(tree.id, turn.seq),
                    root_session_id=tree.id,
                    seq=turn.seq,
                    prompt_text=turn.prompt_text,
                    started_at=turn.started_at,
                    line_no=turn.line_no,
                    message_offset=turn.message_offset,
                ),
            )
        for payload in payloads:
            await session.execute(
                source_records.update()
                .where(
                    source_records.c.root_session_id == tree.id,
                    source_records.c.agent_id == payload.agent_id,
                )
                .values(
                    kind=payload.agent_kind,
                    source_type=payload.source_type,
                    line_count=payload.line_count,
                    processed_at=as_shanghai(completed_at),
                    processed_hash=payload.content_hash,
                    parser_version=parser_version,
                    last_sync_run_id=sync_run_id,
                ),
            )
