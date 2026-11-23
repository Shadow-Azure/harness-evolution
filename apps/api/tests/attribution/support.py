"""Seeding helpers shared by the m10-03 attribution tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import insert
from sqlalchemy.engine import CursorResult

from app.db.base import Database
from app.db.crud.attributions import CandidateWrite, ProbeWrite
from app.db.models.domain import (
    agent_events,
    agents,
    bad_cases,
    session_families,
    source_records,
)
from app.db.models.evolution import evolution_run_candidates, evolution_runs
from app.service.evolution.potential import PotentialCase, TriggerPoint
from app.utils.time import SHANGHAI

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=SHANGHAI)
LATER = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)
SESSION_ID = "96000000-0000-4000-8000-000000000001"
RUN_ID = "run-m10-03-a"
OTHER_RUN_ID = "run-m10-03-b"
CASE_ID = "bc-m10-03-a"
OTHER_CASE_ID = "bc-m10-03-b"
ORPHAN_CASE_ID = "bc-m10-03-orphan"
TARGET_NAME = "deep-research"
TARGET_VERSION = "v2.0.0"
TARGET_REVISION = "tag:v2.0.0"
WORKSPACE_ID = "ws-default"
KNOWLEDGE_DOCUMENT_ID = "KB-READ-001"
KNOWLEDGE_REVISION = "digest:" + "a" * 64


@dataclass(frozen=True, slots=True)
class Harness:
    """One migrated database with runs, cases, candidates, and knowledge evidence."""

    database: Database
    run_id: str = RUN_ID
    other_run_id: str = OTHER_RUN_ID
    case_id: str = CASE_ID
    other_case_id: str = OTHER_CASE_ID
    orphan_case_id: str = ORPHAN_CASE_ID
    session_id: str = SESSION_ID


async def seed_session(database: Database) -> str:
    """Insert the normalized root session and its main Agent."""
    main_agent_id = "agent-m10-03-main"
    async with database.transaction() as session:
        inserted = await session.execute(
            insert(source_records).values(
                root_session_id=SESSION_ID,
                agent_id=main_agent_id,
                kind="main",
                source_type="synthetic",
                line_count=1,
                received_at=NOW,
            ),
        )
        primary_key = cast(CursorResult[object], inserted).inserted_primary_key
        if primary_key is None:
            raise RuntimeError("source record insert returned no primary key")
        await session.execute(
            insert(session_families).values(
                id=SESSION_ID,
                short_title="m10-03 session",
                title="m10-03 session",
                search_text="m10-03 session",
                repo_name="example/repo",
                project_path="/workspace/repo",
                model="glm-5.3",
                models=["glm-5.3"],
                started_at=NOW,
                ended_at=NOW,
                duration_seconds=1,
                status="completed",
                skill_names=[],
                user_turns_count=1,
                messages_count=1,
                tools_count=1,
                errors_count=0,
                agents_count=1,
                tokens_total=10,
                source_type="synthetic",
                main_record_id=int(primary_key[0]),
                imported_at=NOW,
                updated_at=NOW,
            ),
        )
        await session.execute(
            insert(agents).values(
                id=main_agent_id,
                root_session_id=SESSION_ID,
                kind="main",
                tree_index=0,
                spawn_depth=0,
                lines=1,
                messages_count=1,
                tokens_total=10,
                tools_count=1,
                errors_count=0,
                sort_key=0.0,
            ),
        )
    return main_agent_id


async def seed_knowledge_event(database: Database, agent_id: str) -> None:
    """Insert one knowledge document trigger for the root session."""
    async with database.transaction() as session:
        await session.execute(
            insert(agent_events).values(
                agent_id=agent_id,
                event_index=1,
                line_no=2,
                message_offset=1,
                kind="knowledge",
                name="/kb/retrieval.md",
                object_revision=KNOWLEDGE_REVISION,
                triggered_at=NOW,
                document_id=KNOWLEDGE_DOCUMENT_ID,
                document_revision=KNOWLEDGE_REVISION,
                source_path="/kb/retrieval.md",
                retrieval_kind="file_read",
                retrieval_scope="/kb",
            ),
        )


async def seed_case(
    database: Database,
    case_id: str,
    *,
    title: str = "检索索引读取失败",
    description: str = "deep-research 读取索引时未校验快照字段",
    metadata: dict[str, object] | None = None,
    case_type: str = "self",
) -> None:
    """Insert one reported bad case with optional evidence metadata."""
    async with database.transaction() as session:
        await session.execute(
            insert(bad_cases).values(
                bad_case_id=case_id,
                workspace_id=WORKSPACE_ID,
                bad_case_session_id=SESSION_ID,
                bad_case_type=case_type,
                object_name=TARGET_NAME,
                object_type="skill",
                object_version=TARGET_VERSION,
                bad_case_agent_id=None,
                title=title,
                bad_case_description=description,
                meta_data=metadata,
                source="fixtures",
                created_at=NOW,
                updated_at=NOW,
            ),
        )


async def seed_run(
    database: Database,
    run_id: str,
    *,
    attribution_engine: str = "rule-v1",
    cache_enabled: bool = True,
    target_revision: str | None = None,
) -> None:
    """Insert one V2 run with the attribution snapshot columns."""
    async with database.transaction() as session:
        await session.execute(
            insert(evolution_runs).values(
                id=run_id,
                workspace_id=WORKSPACE_ID,
                title=run_id,
                mode="full",
                engine_key="full",
                eval_config={},
                target_type="skill",
                target_name=TARGET_NAME,
                target_version=TARGET_VERSION,
                target_revision=target_revision,
                repo_url="https://example.invalid/skills.git",
                sub_dir="skills/deep-research",
                status="preparing",
                progress_unit=2,
                potential_policy={
                    "preset": "default",
                    "legacyRule": False,
                    "includeSelfReport": True,
                    "includeAfterObject": True,
                    "sameObjectOnly": False,
                },
                cache_enabled=cache_enabled,
                attribution_engine=attribution_engine,
                created_at=NOW,
            ),
        )


async def seed_candidate(
    database: Database,
    run_id: str,
    case_id: str,
    *,
    included: bool = True,
    hit_reason: str = "self_report",
    order_state: str = "comparable",
) -> None:
    """Insert one candidate snapshot that the runner links its probe onto."""
    async with database.transaction() as session:
        await session.execute(
            insert(evolution_run_candidates).values(
                id=f"candidate-{run_id}-{case_id}",
                run_id=run_id,
                workspace_id=WORKSPACE_ID,
                session_id=SESSION_ID,
                bad_case_id=case_id,
                object_trigger_agent_id="agent-m10-03-main",
                object_trigger_event_index=0,
                object_trigger_at=NOW,
                case_trigger_agent_id="agent-m10-03-main",
                case_trigger_event_index=1,
                case_trigger_at=LATER,
                order_state=order_state,
                included=included,
                included_reason=hit_reason,
                probe_id=None,
                is_cached=False,
                created_at=NOW,
            ),
        )


def probe_write(
    case_id: str = CASE_ID,
    *,
    probe_id: str = "probe-m10-03-a",
    object_version: str | None = TARGET_REVISION,
    conclusion: str = "attributed",
    attribute_type: str | None = "error",
    created_run_id: str = RUN_ID,
    description: str = "description",
    confidence: float = 0.8,
    engine: str = "rule-v1",
    updated_at: datetime = NOW,
) -> ProbeWrite:
    """Build one V2 probe write with deterministic defaults."""
    return ProbeWrite(
        probe_id=probe_id,
        workspace_id=WORKSPACE_ID,
        session_id=SESSION_ID,
        bad_case_id=case_id,
        probe_type="skill",
        probe_object=TARGET_NAME,
        object_version=object_version,
        attribute_type=attribute_type,
        conclusion=conclusion,
        confidence=confidence,
        probe_description=description,
        probe_analysis="analysis",
        policy_version="v1",
        attribution_engine=engine,
        created_run_id=created_run_id,
        created_at=NOW,
        updated_at=updated_at,
    )


def candidate_write(
    case_id: str = CASE_ID,
    *,
    run_id: str = RUN_ID,
    included: bool = True,
    hit_reason: str = "self_report",
    order_state: str = "comparable",
) -> CandidateWrite:
    """Build one candidate write for repository-level tests."""
    return CandidateWrite(
        id=f"candidate-write-{run_id}-{case_id}",
        run_id=run_id,
        workspace_id=WORKSPACE_ID,
        session_id=SESSION_ID,
        bad_case_id=case_id,
        object_trigger_agent_id="agent-m10-03-main",
        object_trigger_event_index=0,
        object_trigger_at=NOW,
        case_trigger_agent_id="agent-m10-03-main",
        case_trigger_event_index=1,
        case_trigger_at=LATER,
        order_state=order_state,  # type: ignore[arg-type]
        included=included,
        included_reason=hit_reason,  # type: ignore[arg-type]
        created_at=NOW,
    )


def potential_case(
    case_id: str = CASE_ID,
    *,
    included: bool = True,
    hit_reason: str = "self_report",
    order_state: str = "comparable",
    bad_case_type: str = "self",
) -> PotentialCase:
    """Build the matcher row the runner consumes."""
    return PotentialCase(
        bad_case_id=case_id,
        session_id=SESSION_ID,
        object_name=TARGET_NAME,
        bad_case_type=bad_case_type,
        trigger_at=NOW,
        hit_reason=hit_reason,  # type: ignore[arg-type]
        order_state=order_state,  # type: ignore[arg-type]
        included=included,
        object_trigger=TriggerPoint(
            agent_id="agent-m10-03-main",
            event_index=0,
            triggered_at=NOW,
            tree_index=0,
        ),
        case_trigger=TriggerPoint(
            agent_id="agent-m10-03-main",
            event_index=1,
            triggered_at=LATER,
            tree_index=0,
        ),
    )
