"""Root-sync source selection, freezing, traversal, and runtime propagation."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_case_sync import BadCaseRootSyncRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_cases, trajectory_payloads
from app.errors import AppError, ErrorCode
from app.service.acquisition.bad_case_sync import BadCaseRootSyncService
from app.service.acquisition.parsers import (
    AgentMetaFacts,
    BaseTraceParser,
    ParseContext,
    TraceParserFactory,
    TracePayload,
    UnsupportedTraceRuntime,
)
from app.service.acquisition.parsers.base import _dict, _string
from app.third_party_api.session_query.models import SessionTrajectory
from app.third_party_api.session_source import SessionInfo
from app.utils.time import now_shanghai

ROOT = "root-session-1"
CHILD = "agent-child-1"
TEMPLATE_A = "https://trace-a.test/api/sessions/{sessionId}"
TEMPLATE_B = "https://trace-b.test/api/sessions/{sessionId}"


def jsonl(*records: object) -> str:
    """Encode deterministic fake-runtime JSONL."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def fake_trajectory() -> SessionTrajectory:
    """Return a minimal transcript the fake parser accepts."""
    content = jsonl(
        {"event": "user", "at": "2026-11-16T10:00:00Z", "prompt": "hello"},
        {"event": "assistant", "id": "m1", "model": "fake", "at": "2026-11-16T10:00:01Z"},
    )
    return SessionTrajectory(content=content, line_count=2)


class FakeTraceParser(BaseTraceParser):
    """Minimal second runtime so replay accepts the propagated runtime_key."""

    runtime_key = "fake-runtime"
    parser_version = 1

    @classmethod
    def can_parse(cls, payloads: Sequence[TracePayload]) -> bool:
        """Accept only the fake event schema used by this module."""
        if not payloads:
            return False
        for payload in payloads:
            first_line = next(
                (line for line in payload.content.splitlines() if line.strip()),
                "",
            )
            try:
                first = json.loads(first_line)
            except json.JSONDecodeError:
                return False
            if not isinstance(first, dict) or "event" not in first or "type" in first:
                return False
        return True

    def consume_record(
        self,
        record: dict[str, object],
        ctx: ParseContext,
        line_no: int,
    ) -> None:
        event = record.get("event")
        timestamp = ctx.observe_timestamp(record.get("at"))
        if event == "user":
            prompt = _string(record.get("prompt"))
            if prompt is not None:
                ctx.record_user_turn(prompt, timestamp, line_no)
            ctx.mark_user_input()
            return
        if event != "assistant":
            return
        ctx.mark_assistant_record(fatal_error_unrecovered=False)
        ctx.record_assistant_message(
            message_id=_string(record.get("id")),
            model=_string(record.get("model")),
            usage=_dict(record.get("usage")),
        )

    def parse_agent_meta(self, meta: Mapping[str, object]) -> AgentMetaFacts:
        return AgentMetaFacts(spawn_depth=0)


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide one migrated SQLite database isolated per test."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("m9-07-source-test-secret"),
    )
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


@pytest.fixture(autouse=True)
def fake_parser() -> Iterator[None]:
    """Register the fake parser for this module and restore the registry."""
    saved = dict(TraceParserFactory._parsers)
    TraceParserFactory.register(FakeTraceParser)
    try:
        yield
    finally:
        TraceParserFactory._parsers.clear()
        TraceParserFactory._parsers.update(saved)


async def insert_case(
    database: Database,
    *,
    bad_case_id: str,
    session_source: Mapping[str, object] | None = None,
    created_at: Any = None,
) -> None:
    """Insert one reported case directly under the test root."""
    now = created_at or now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            bad_cases.insert().values(
                bad_case_id=bad_case_id,
                bad_case_session_id=ROOT,
                bad_case_type="self",
                object_name="deep-research",
                object_type="skill",
                object_version="v1",
                bad_case_agent_id=None,
                title="case",
                bad_case_description="description",
                meta_data=None,
                source="test",
                session_source=session_source,
                created_at=now,
                updated_at=now,
            ),
        )


@dataclass
class FakeFetcher:
    """Stand-in for the HTTP envelope client used by the sync service."""

    tree: dict[str, tuple[str, ...]] = field(default_factory=dict)
    calls: list[dict[str, object]] = field(default_factory=list)
    failure: Exception | None = None

    async def fetch(
        self,
        *,
        session_url_template: str,
        session_id: str,
        expected_parent_id: str | None,
        declared_runtime: str | None = None,
    ) -> SessionInfo:
        self.calls.append(
            {
                "template": session_url_template,
                "session_id": session_id,
                "parent": expected_parent_id,
                "runtime": declared_runtime,
            },
        )
        if self.failure is not None:
            raise self.failure
        is_root = expected_parent_id is None
        return SessionInfo(
            runtime_key="fake-runtime",
            agent_kind="main" if is_root else "subagent",
            parent_agent_id=expected_parent_id,
            child_session_ids=self.tree.get(session_id, ()),
            agent_meta=(
                None if is_root else {"parentAgentId": expected_parent_id, "toolUseId": "tool-1"}
            ),
            trajectory=fake_trajectory(),
            runtime_version="1",
        )


@dataclass
class FakeGlobalSource:
    """Legacy global query source that must not be called for report roots."""

    calls: list[str] = field(default_factory=list)

    async def list_children(self, session_id: str) -> tuple[str, ...]:
        self.calls.append(session_id)
        return ()

    async def fetch_trajectory(self, session_id: str) -> SessionTrajectory:
        self.calls.append(session_id)
        return SessionTrajectory(content=jsonl({"type": "user"}), line_count=1)

    async def close(self) -> None:
        return None


def service(
    database: Database,
    *,
    global_source: FakeGlobalSource | None,
    fetcher: FakeFetcher | None,
) -> BadCaseRootSyncService:
    return BadCaseRootSyncService(
        database,
        BadCaseRootSyncRepository(database),
        global_source,
        session_source_fetcher=fetcher,
        batch_size=10,
        time_budget_seconds=60,
        max_agents=10,
        max_depth=5,
        lease_seconds=60,
    )


async def payload_rows(database: Database) -> list[dict[str, Any]]:
    async with database.session() as session:
        rows = (
            (
                await session.execute(
                    select(trajectory_payloads).where(
                        trajectory_payloads.c.root_session_id == ROOT,
                    ),
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


@pytest.mark.asyncio
async def test_report_source_is_selected_and_frozen(database: Database) -> None:
    """A per-report template drives traversal and persists a report snapshot."""
    await insert_case(
        database,
        bad_case_id="case-1",
        session_source={"runtime": "fake-runtime", "sessionUrlTemplate": TEMPLATE_A},
    )
    global_source = FakeGlobalSource()
    fetcher = FakeFetcher(tree={ROOT: (CHILD,), CHILD: ()})

    result = await service(database, global_source=global_source, fetcher=fetcher).run(
        owner="job-1",
        now=now_shanghai(),
    )

    assert result.roots_synced == 1
    assert result.agents_fetched == 2
    assert global_source.calls == []
    assert [call["template"] for call in fetcher.calls] == [TEMPLATE_A, TEMPLATE_A]
    assert [call["parent"] for call in fetcher.calls] == [None, ROOT]

    rows = await payload_rows(database)
    by_id = {row["agent_id"]: row for row in rows}
    assert set(by_id) == {ROOT, CHILD}
    assert by_id[ROOT]["runtime_key"] == "fake-runtime"
    assert by_id[ROOT]["agent_kind"] == "main"
    assert by_id[ROOT]["agent_meta"] is None
    assert by_id[CHILD]["agent_kind"] == "subagent"
    assert by_id[CHILD]["agent_meta"] == {"parentAgentId": ROOT, "toolUseId": "tool-1"}

    state = await BadCaseRootSyncRepository(database).get(ROOT)
    assert state is not None
    assert state.status == "synced"
    assert state.source_kind == "report"
    assert state.source_snapshot == {
        "kind": "report",
        "runtime": "fake-runtime",
        "session_url_template": TEMPLATE_A,
    }


@pytest.mark.asyncio
async def test_global_fallback_keeps_the_existing_claude_path(database: Database) -> None:
    """A root without a report source falls back to the global two-endpoint path."""
    await insert_case(database, bad_case_id="case-1")
    global_source = FakeGlobalSource()
    fetcher = FakeFetcher()

    result = await service(database, global_source=global_source, fetcher=fetcher).run(
        owner="job-1",
        now=now_shanghai(),
    )

    assert result.roots_synced == 1
    assert fetcher.calls == []
    assert global_source.calls == [ROOT, ROOT]

    rows = await payload_rows(database)
    assert [row["runtime_key"] for row in rows] == ["claude-code"]
    state = await BadCaseRootSyncRepository(database).get(ROOT)
    assert state is not None
    assert state.source_kind == "global"
    assert state.source_snapshot == {"kind": "global"}


@pytest.mark.asyncio
async def test_retry_does_not_switch_the_frozen_source(database: Database) -> None:
    """A retry reuses the first claim's template even when a newer report arrives."""
    await insert_case(
        database,
        bad_case_id="case-1",
        session_source={"runtime": "fake-runtime", "sessionUrlTemplate": TEMPLATE_A},
    )
    fetcher = FakeFetcher(
        failure=AppError(
            status_code=502,
            code=ErrorCode.SESSION_SOURCE_TIMEOUT,
            message="timeout",
        ),
    )
    first_now = now_shanghai()
    await service(database, global_source=None, fetcher=fetcher).run(
        owner="job-1",
        now=first_now,
    )

    failed = await BadCaseRootSyncRepository(database).get(ROOT)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.last_error == "SESSION_SOURCE_TIMEOUT"
    assert failed.source_snapshot is not None
    assert failed.source_snapshot["session_url_template"] == TEMPLATE_A

    await insert_case(
        database,
        bad_case_id="case-2",
        session_source={"runtime": "fake-runtime", "sessionUrlTemplate": TEMPLATE_B},
        created_at=first_now + timedelta(seconds=1),
    )
    fetcher.failure = None
    second_now = first_now + timedelta(minutes=2)
    await service(database, global_source=None, fetcher=fetcher).run(
        owner="job-2",
        now=second_now,
    )

    assert [call["template"] for call in fetcher.calls] == [TEMPLATE_A, TEMPLATE_A]


@pytest.mark.asyncio
async def test_unknown_runtime_fails_with_a_stable_code(database: Database) -> None:
    """An unregistered envelope runtime fails the root without Claude fallback."""
    await insert_case(
        database,
        bad_case_id="case-1",
        session_source={"runtime": "opencode", "sessionUrlTemplate": TEMPLATE_A},
    )
    fetcher = FakeFetcher(failure=UnsupportedTraceRuntime("opencode"))

    result = await service(database, global_source=None, fetcher=fetcher).run(
        owner="job-1",
        now=now_shanghai(),
    )

    assert result.roots_failed == 1
    assert await payload_rows(database) == []
    state = await BadCaseRootSyncRepository(database).get(ROOT)
    assert state is not None
    assert state.status == "failed"
    assert state.last_error == "UNSUPPORTED_RUNTIME"


@pytest.mark.asyncio
async def test_latest_report_source_prefers_newest_then_largest_id(database: Database) -> None:
    """The source selection is deterministic for equal timestamps."""
    base = now_shanghai()
    await insert_case(
        database,
        bad_case_id="case-1",
        session_source={"runtime": "fake-runtime", "sessionUrlTemplate": TEMPLATE_A},
        created_at=base,
    )
    await insert_case(
        database,
        bad_case_id="case-2",
        session_source={"runtime": "fake-runtime", "sessionUrlTemplate": TEMPLATE_B},
        created_at=base,
    )
    repository = BadCaseRootSyncRepository(database)

    selected = await repository.latest_report_source(ROOT)

    assert selected is not None
    assert selected.session_url_template == TEMPLATE_B


@pytest.mark.asyncio
async def test_repository_detects_report_sources_for_availability(database: Database) -> None:
    """A report-only deployment can schedule sync without a global service."""
    repository = BadCaseRootSyncRepository(database)
    assert await repository.has_report_source() is False

    await insert_case(
        database,
        bad_case_id="case-1",
        session_source={"runtime": "fake-runtime", "sessionUrlTemplate": TEMPLATE_A},
    )

    assert await repository.has_report_source() is True
