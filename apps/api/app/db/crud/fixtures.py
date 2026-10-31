"""Transactional and idempotent seed support for deterministic fixture corpora."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Column, Table, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ServicePhase, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agent_events,
    agents,
    bad_case_analysis,
    bad_cases,
    evolution_targets,
    probe_reports,
    session_families,
    source_records,
    trajectory_payloads,
    user_turns,
)
from app.fixture_corpus import FixtureCorpus
from app.utils.time import as_shanghai


class SeedEnvironmentError(RuntimeError):
    """Raised when seed data is requested outside a development target."""


@dataclass(frozen=True, slots=True)
class CorpusSeedResult:
    """Stable output from one idempotent synthetic-corpus seed run."""

    inserted: int
    changed: int
    root_sessions: int
    payloads: int
    agents: int
    status: str = "seeded"


_UPSERT_KEYS: dict[Table, tuple[Column[Any], ...]] = {
    trajectory_payloads: (
        trajectory_payloads.c.root_session_id,
        trajectory_payloads.c.agent_id,
    ),
    source_records: (source_records.c.root_session_id, source_records.c.agent_id),
    session_families: (session_families.c.id,),
    agents: (agents.c.id,),
    agent_events: (agent_events.c.agent_id, agent_events.c.event_index),
    user_turns: (user_turns.c.id,),
    probe_reports: (probe_reports.c.probe_id,),
    bad_cases: (bad_cases.c.bad_case_id,),
    bad_case_analysis: (bad_case_analysis.c.bad_case_id,),
    evolution_targets: (evolution_targets.c.id,),
}

_INSERT_ONLY_COLUMNS: dict[Table, frozenset[str]] = {
    source_records: frozenset(
        {
            "received_at",
            "processed_at",
            "processed_hash",
            "parser_version",
            "last_sync_run_id",
        },
    ),
    evolution_targets: frozenset({"created_by"}),
}


async def ensure_fixture_external_tables(database: Database) -> None:
    """Create development-only external tables when the application migrated first."""
    tables = (bad_cases, probe_reports, bad_case_analysis)

    def create(sync_connection: object) -> None:
        bad_cases.metadata.create_all(
            sync_connection,  # type: ignore[arg-type]
            tables=tables,
            checkfirst=True,
        )

    async with database.engine.begin() as connection:
        await connection.run_sync(create)


def _comparable(value: object) -> object:
    """Normalize dialect datetime reflection for deterministic comparisons."""
    if isinstance(value, datetime):
        return as_shanghai(value).replace(tzinfo=None)
    return value


async def _upsert(
    session: AsyncSession,
    table: Table,
    values: dict[str, object],
) -> tuple[int, int]:
    """Insert a stable-key row or update changed fixture-owned columns."""
    key_columns = _UPSERT_KEYS[table]
    conditions = [column == values[column.name] for column in key_columns]
    existing = (await session.execute(select(table).where(*conditions))).mappings().one_or_none()
    if existing is None:
        await session.execute(table.insert().values(**values))
        return 1, 0
    insert_only = _INSERT_ONLY_COLUMNS.get(table, frozenset())
    fixture_owned = {name: value for name, value in values.items() if name not in insert_only}
    if all(
        _comparable(existing[name]) == _comparable(value)
        for name, value in fixture_owned.items()
        if name not in {column.name for column in key_columns}
    ):
        return 0, 0
    await session.execute(update(table).where(*conditions).values(**fixture_owned))
    return 0, 1


async def _source_record_id(
    session: AsyncSession,
    *,
    root_session_id: str,
    agent_id: str,
) -> int:
    """Return the processing index id for one agent payload."""
    value: int = (
        await session.execute(
            select(source_records.c.id).where(
                source_records.c.root_session_id == root_session_id,
                source_records.c.agent_id == agent_id,
            ),
        )
    ).scalar_one()
    return int(value)


async def _seed_corpus(database: Database, corpus: FixtureCorpus) -> CorpusSeedResult:
    """Write one validated corpus in a single rollback-safe transaction."""
    inserted = 0
    changed = 0
    async with database.transaction() as session:
        for session_fixture in corpus.root_sessions:
            for agent in session_fixture.agents:
                if not agent.has_payload:
                    continue
                payload_writes = await _upsert(
                    session,
                    trajectory_payloads,
                    {
                        "root_session_id": session_fixture.id,
                        "agent_id": agent.record.id,
                        "agent_kind": agent.record.kind,
                        "payload": agent.content,
                        "agent_meta": agent.record.meta,
                        "content_hash": agent.content_hash,
                        "line_count": agent.line_count,
                        "source_type": session_fixture.record.source_type,
                        "updated_at": as_shanghai(session_fixture.record.updated_at),
                    },
                )
                inserted += payload_writes[0]
                changed += payload_writes[1]
                source_writes = await _upsert(
                    session,
                    source_records,
                    {
                        "root_session_id": session_fixture.id,
                        "agent_id": agent.record.id,
                        "kind": agent.record.kind,
                        "source_type": session_fixture.record.source_type,
                        "line_count": agent.line_count,
                        "received_at": as_shanghai(session_fixture.record.imported_at),
                        "processed_at": None,
                        "processed_hash": None,
                        "parser_version": None,
                        "last_sync_run_id": None,
                    },
                )
                inserted += source_writes[0]
                changed += source_writes[1]

        trajectory_count = sum(
            1 for root in corpus.root_sessions for agent in root.agents if agent.has_payload
        )
        for session_fixture in corpus.root_sessions:
            record = session_fixture.record
            main_agent = next(
                agent for agent in session_fixture.agents if agent.record.kind == "main"
            )
            main_record_id = await _source_record_id(
                session,
                root_session_id=record.id,
                agent_id=main_agent.record.id,
            )
            models = sorted(
                {
                    agent.record.model
                    for agent in session_fixture.agents
                    if agent.record.model is not None
                },
            )
            skill_names = sorted(
                {
                    event.name
                    for agent in session_fixture.agents
                    for event in agent.record.events
                    if event.kind == "skill" and event.name is not None
                },
            )
            family_writes = await _upsert(
                session,
                session_families,
                {
                    "id": record.id,
                    "short_title": record.short_title,
                    "title": record.title,
                    "search_text": f"{record.title} {record.repo_name}".lower(),
                    "repo_name": record.repo_name,
                    "project_path": record.project_path,
                    "git_branch": record.git_branch,
                    "cli_version": record.cli_version,
                    "entrypoint": record.entrypoint,
                    "model": main_agent.record.model,
                    "models": models,
                    "started_at": as_shanghai(record.started_at),
                    "ended_at": as_shanghai(record.ended_at),
                    "duration_seconds": int(
                        (record.ended_at - record.started_at).total_seconds(),
                    ),
                    "status": record.status,
                    "skill_names": skill_names,
                    "user_turns_count": sum(
                        len(agent.record.user_turns) for agent in session_fixture.agents
                    ),
                    "messages_count": sum(
                        agent.record.messages_count for agent in session_fixture.agents
                    ),
                    "tools_count": sum(
                        agent.record.tools_count for agent in session_fixture.agents
                    ),
                    "errors_count": sum(
                        agent.record.errors_count for agent in session_fixture.agents
                    ),
                    "agents_count": sum(
                        1
                        for agent in session_fixture.agents
                        if agent.record.kind == "subagent"
                        and agent.record.task_kind != "forked_skill"
                    ),
                    "tokens_total": sum(
                        agent.record.tokens_total for agent in session_fixture.agents
                    ),
                    "source_type": record.source_type,
                    "main_record_id": main_record_id,
                    "imported_at": as_shanghai(record.imported_at),
                    "updated_at": as_shanghai(record.updated_at),
                },
            )
            inserted += family_writes[0]
            changed += family_writes[1]

        for session_fixture in corpus.root_sessions:
            for agent in sorted(
                session_fixture.agents,
                key=lambda item: (item.record.spawn_depth, item.record.sort_key),
            ):
                transcript_record_id = (
                    await _source_record_id(
                        session,
                        root_session_id=session_fixture.id,
                        agent_id=agent.record.id,
                    )
                    if agent.has_payload
                    else None
                )
                agent_writes = await _upsert(
                    session,
                    agents,
                    {
                        "id": agent.record.id,
                        "root_session_id": session_fixture.id,
                        "parent_agent_id": agent.record.parent_agent_id,
                        "kind": agent.record.kind,
                        "agent_type": agent.record.agent_type,
                        "task_kind": agent.record.task_kind,
                        "team_name": agent.record.team_name,
                        "name": agent.record.name,
                        "skill_name": agent.record.skill_name,
                        "model": agent.record.model,
                        "requested_model": agent.record.requested_model,
                        "description": agent.record.description,
                        "tool_use_id": agent.record.tool_use_id,
                        "spawn_depth": agent.record.spawn_depth,
                        "transcript_record_id": transcript_record_id,
                        "lines": agent.line_count,
                        "messages_count": agent.record.messages_count,
                        "tokens_total": agent.record.tokens_total,
                        "tools_count": agent.record.tools_count,
                        "errors_count": agent.record.errors_count,
                        "meta": agent.record.meta,
                        "sort_key": agent.record.sort_key,
                    },
                )
                inserted += agent_writes[0]
                changed += agent_writes[1]

        for session_fixture in corpus.root_sessions:
            for agent in session_fixture.agents:
                for event in agent.record.events:
                    event_writes = await _upsert(
                        session,
                        agent_events,
                        {
                            "agent_id": agent.record.id,
                            "event_index": event.event_index,
                            "line_no": event.line_no,
                            "message_offset": event.message_offset,
                            "kind": event.kind,
                            "name": event.name,
                            "description": event.description,
                            "tool_use_id": event.tool_use_id,
                        },
                    )
                    inserted += event_writes[0]
                    changed += event_writes[1]
                for turn in agent.record.user_turns:
                    turn_writes = await _upsert(
                        session,
                        user_turns,
                        {
                            "id": turn.id,
                            "root_session_id": session_fixture.id,
                            "seq": turn.seq,
                            "prompt_text": turn.prompt_text,
                            "started_at": as_shanghai(turn.started_at),
                            "line_no": turn.line_no,
                            "message_offset": turn.message_offset,
                        },
                    )
                    inserted += turn_writes[0]
                    changed += turn_writes[1]

        for probe in corpus.manifest.probe_reports:
            probe_writes = await _upsert(
                session,
                probe_reports,
                {
                    "probe_id": probe.probe_id,
                    "session_id": probe.session_id,
                    "probe_type": probe.probe_type,
                    "probe_object": probe.probe_object,
                    "object_version": probe.object_version,
                    "attribute_type": probe.attribute_type,
                    "probe_description": probe.probe_description,
                    "probe_analysis": probe.probe_analysis,
                    "created_at": as_shanghai(probe.created_at),
                    "updated_at": as_shanghai(probe.updated_at),
                },
            )
            inserted += probe_writes[0]
            changed += probe_writes[1]

        for case in corpus.manifest.bad_cases:
            case_writes = await _upsert(
                session,
                bad_cases,
                {
                    "bad_case_id": case.bad_case_id,
                    "bad_case_session_id": case.bad_case_session_id,
                    "bad_case_type": case.bad_case_type,
                    "object_name": case.object_name,
                    "object_type": case.object_type,
                    "object_version": case.object_version,
                    "bad_case_agent_id": case.bad_case_agent_id,
                    "title": case.title,
                    "bad_case_description": case.reason,
                    "meta_data": case.meta_data,
                    "source": case.source,
                    "created_at": as_shanghai(case.created_at),
                    "updated_at": as_shanghai(case.updated_at),
                },
            )
            inserted += case_writes[0]
            changed += case_writes[1]

        for analysis in corpus.manifest.bad_case_analyses:
            analysis_writes = await _upsert(
                session,
                bad_case_analysis,
                {
                    "bad_case_id": analysis.bad_case_id,
                    "analysis_status": analysis.analysis_status,
                    "probe_id": analysis.probe_id,
                    "analysis_result": analysis.analysis_result,
                    "updated_at": as_shanghai(analysis.updated_at),
                },
            )
            inserted += analysis_writes[0]
            changed += analysis_writes[1]

        for target in corpus.manifest.evolution_targets:
            target_writes = await _upsert(
                session,
                evolution_targets,
                {
                    "id": target.id,
                    "object_type": target.object_type,
                    "object_name": target.object_name,
                    "repo_url": target.repo_url,
                    "sub_dir": target.sub_dir,
                    "default_ref": target.default_ref,
                    "validation_project_id": target.validation_project_id,
                    "test_project_id": target.test_project_id,
                    "enabled": target.enabled,
                    "created_by": None,
                    "created_at": as_shanghai(target.created_at),
                    "updated_at": as_shanghai(target.updated_at),
                },
            )
            inserted += target_writes[0]
            changed += target_writes[1]

    return CorpusSeedResult(
        inserted=inserted,
        changed=changed,
        root_sessions=len(corpus.root_sessions),
        payloads=trajectory_count,
        agents=len(corpus.agents),
        status="seeded" if inserted or changed else "noop",
    )


async def run_corpus_seed(settings: Settings, corpus: FixtureCorpus) -> CorpusSeedResult:
    """Validate the target environment, migrate, and apply one fixture corpus."""
    if settings.production:
        raise SeedEnvironmentError("fixture seed refuses a production target")
    if settings.phase is ServicePhase.LIVE:
        raise SeedEnvironmentError("fixture seed refuses a live target")
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database, bootstrap_external_tables=False)
        await ensure_fixture_external_tables(database)
        return await _seed_corpus(database, corpus)
    finally:
        await database.dispose()
