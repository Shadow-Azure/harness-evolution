"""Stable-key persistence for development-only local session payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.db.base import Database
from app.db.models.domain import source_records, trajectory_payloads

if TYPE_CHECKING:
    from app.service.acquisition.local_sessions import LocalAgentPayload


@dataclass(frozen=True, slots=True)
class LocalImportWriteResult:
    """Counts for payload and processing-index writes."""

    inserted_payloads: int
    updated_payloads: int
    unchanged_payloads: int
    inserted_source_records: int
    updated_source_records: int


def _comparable(value: object) -> object:
    """Normalize database datetime reflection for stable comparisons."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return value


async def write_local_payloads(
    database: Database,
    payloads: tuple[LocalAgentPayload, ...],
) -> LocalImportWriteResult:
    """Insert or update local payloads in one rollback-safe transaction."""
    inserted_payloads = 0
    updated_payloads = 0
    unchanged_payloads = 0
    inserted_source_records = 0
    updated_source_records = 0
    async with database.transaction() as session:
        for payload in payloads:
            key = (
                trajectory_payloads.c.root_session_id == payload.root_session_id,
                trajectory_payloads.c.agent_id == payload.agent_id,
            )
            existing = (
                (await session.execute(select(trajectory_payloads).where(*key)))
                .mappings()
                .one_or_none()
            )
            values = {
                "root_session_id": payload.root_session_id,
                "agent_id": payload.agent_id,
                "agent_kind": payload.agent_kind,
                "payload": payload.content,
                "agent_meta": payload.agent_meta,
                "content_hash": payload.content_hash,
                "line_count": payload.line_count,
                "source_type": "script",
                "updated_at": payload.source_updated_at,
            }
            if existing is None:
                await session.execute(trajectory_payloads.insert().values(**values))
                inserted_payloads += 1
            else:
                changed = {
                    name: value
                    for name, value in values.items()
                    if name not in {"root_session_id", "agent_id"}
                    and _comparable(existing[name]) != _comparable(value)
                }
                if changed:
                    await session.execute(
                        trajectory_payloads.update().where(*key).values(**changed),
                    )
                    updated_payloads += 1
                else:
                    unchanged_payloads += 1

            source_key = (
                source_records.c.root_session_id == payload.root_session_id,
                source_records.c.agent_id == payload.agent_id,
            )
            existing_source = (
                (await session.execute(select(source_records).where(*source_key)))
                .mappings()
                .one_or_none()
            )
            if existing_source is None:
                await session.execute(
                    source_records.insert().values(
                        root_session_id=payload.root_session_id,
                        agent_id=payload.agent_id,
                        kind=payload.agent_kind,
                        source_type="script",
                        line_count=payload.line_count,
                        received_at=payload.discovered_at,
                        processed_at=None,
                        processed_hash=None,
                        parser_version=None,
                        last_sync_run_id=None,
                    ),
                )
                inserted_source_records += 1
            else:
                source_changes = {
                    name: value
                    for name, value in {
                        "kind": payload.agent_kind,
                        "source_type": "script",
                        "line_count": payload.line_count,
                    }.items()
                    if _comparable(existing_source[name]) != _comparable(value)
                }
                if source_changes:
                    await session.execute(
                        source_records.update().where(*source_key).values(**source_changes),
                    )
                    updated_source_records += 1
    return LocalImportWriteResult(
        inserted_payloads=inserted_payloads,
        updated_payloads=updated_payloads,
        unchanged_payloads=unchanged_payloads,
        inserted_source_records=inserted_source_records,
        updated_source_records=updated_source_records,
    )


async def count_local_session_rows(database: Database) -> tuple[int, int]:
    """Return payload and processing-index row counts."""
    async with database.session() as session:
        payload_rows = len((await session.execute(select(trajectory_payloads))).all())
        source_rows = len((await session.execute(select(source_records))).all())
    return payload_rows, source_rows


async def list_local_session_keys(database: Database) -> set[tuple[str, str]]:
    """Return all persisted payload identities."""
    async with database.session() as session:
        rows = (
            await session.execute(
                select(
                    trajectory_payloads.c.root_session_id,
                    trajectory_payloads.c.agent_id,
                ),
            )
        ).all()
    return {(str(row[0]), str(row[1])) for row in rows}
