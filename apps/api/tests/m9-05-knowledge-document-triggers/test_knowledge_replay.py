"""Knowledge-document evidence through replay and the Session API."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import SecretStr
from sqlalchemy import select, text

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agent_events,
    bad_cases,
    source_records,
    trajectory_payloads,
)
from app.db.models.workspace import workspaces
from app.main import create_app
from app.service.acquisition.replay import replay_pending_payloads
from app.utils.definition import definition_hash
from app.utils.knowledge_paths import knowledge_document_id
from app.utils.time import now_shanghai
from tests.workspaces.helpers import bearer

ROOT_ID = "93000000-0000-4000-8000-000000000001"
WORKSPACE_A = "ws-knowledge-a"
WORKSPACE_B = "ws-knowledge-b"
KNOWLEDGE_ROOT_A = "/workspace/knowledge"
KNOWLEDGE_ROOT_B = "/workspace/shared/kb"
SOURCE_ROOT = "/workspace/repository"


def jsonl(*records: object) -> str:
    """Encode deterministic JSONL test input."""
    return "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"


def user(text: str = "synthetic task") -> dict[str, object]:
    """Build one user turn with an explicit timestamp."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": "2026-11-16T01:00:00Z",
        "message": {"content": text},
    }


def read_call(
    tool_id: str,
    path: str,
    *,
    timestamp: str = "2026-11-16T01:01:00Z",
) -> dict[str, object]:
    """Build one assistant record holding a single Read call."""
    return {
        "type": "assistant",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "id": f"message-{tool_id}",
            "model": "model-main",
            "stop_reason": "tool_use",
            "content": [
                {"type": "tool_use", "id": tool_id, "name": "Read", "input": {"file_path": path}},
            ],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
    }


def read_result(
    tool_id: str,
    path: str,
    content: str,
    *,
    timestamp: str = "2026-11-16T01:02:00Z",
) -> dict[str, object]:
    """Build one complete Read tool result."""
    return {
        "type": "user",
        "sessionId": ROOT_ID,
        "timestamp": timestamp,
        "message": {
            "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "read result"}],
        },
        "toolUseResult": {
            "type": "text",
            "file": {
                "filePath": path,
                "content": content,
                "startLine": 1,
                "numLines": content.count("\n"),
                "totalLines": content.count("\n"),
            },
        },
    }


MAIN_CONTENT = jsonl(
    user(),
    read_call("tool-knowledge-a", f"{KNOWLEDGE_ROOT_A}/guides/runbook.md"),
    read_result("tool-knowledge-a", f"{KNOWLEDGE_ROOT_A}/guides/runbook.md", "Runbook\nbody\n"),
    read_call("tool-knowledge-b", f"{KNOWLEDGE_ROOT_B}/team/oncall.md"),
    read_result("tool-knowledge-b", f"{KNOWLEDGE_ROOT_B}/team/oncall.md", "On-call\nbody\n"),
    read_call("tool-source", f"{SOURCE_ROOT}/src/app.py"),
    read_result("tool-source", f"{SOURCE_ROOT}/src/app.py", "print('app')\n"),
)


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database for one replay test."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'knowledge.db'}",
        data_dir=tmp_path,
        jwt_secret=SecretStr("knowledge-document-trigger-test-secret"),
        admin_username="admin",
        admin_password=SecretStr("initial-password"),
    )


async def seed_payload(
    database: Database,
    content: str = MAIN_CONTENT,
) -> None:
    """Insert one raw payload as an external pull would."""
    async with database.transaction() as session:
        await session.execute(
            trajectory_payloads.insert().values(
                runtime_key="claude-code",
                root_session_id=ROOT_ID,
                agent_id=ROOT_ID,
                agent_kind="main",
                payload=content,
                agent_meta=None,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                line_count=len(content.splitlines()),
                source_type="script",
                updated_at=datetime(2026, 11, 16, 2, tzinfo=UTC),
            ),
        )


async def seed_workspace(
    database: Database,
    *,
    workspace_id: str,
    name: str,
    knowledge_roots: list[str],
    bad_case_id: str,
    bad_case_session_id: str | None = None,
) -> None:
    """Insert one workspace, its optional knowledge roots, and one reported case."""
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            workspaces.insert().values(
                id=workspace_id,
                name=name,
                mark=name,
                quota=10,
                status="active",
                knowledge_roots=knowledge_roots,
                created_at=now,
                updated_at=now,
            ),
        )
        await session.execute(
            bad_cases.insert().values(
                bad_case_id=bad_case_id,
                workspace_id=workspace_id,
                bad_case_session_id=bad_case_session_id or ROOT_ID,
                bad_case_type="self",
                object_name="knowledge-doc",
                object_type="skill",
                title=f"Case {bad_case_id}",
                bad_case_description="Synthetic knowledge trigger replay case.",
                created_at=now,
                updated_at=now,
            ),
        )


async def test_replay_persists_knowledge_documents_from_every_reported_root(
    tmp_path: Path,
) -> None:
    """Roots from every workspace that reported the root session are unioned."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_payload(database)
        await seed_workspace(
            database,
            workspace_id=WORKSPACE_A,
            name="Knowledge A",
            knowledge_roots=[KNOWLEDGE_ROOT_A],
            bad_case_id="bc-knowledge-a",
        )
        await seed_workspace(
            database,
            workspace_id=WORKSPACE_B,
            name="Knowledge B",
            knowledge_roots=[KNOWLEDGE_ROOT_B],
            bad_case_id="bc-knowledge-b",
        )

        result = await replay_pending_payloads(database)

        async with database.session() as session:
            rows = (await session.execute(select(agent_events))).mappings().all()
            source_version: int = int(
                (
                    await session.execute(
                        select(source_records.c.parser_version).where(
                            source_records.c.root_session_id == ROOT_ID,
                        ),
                    )
                ).scalar_one(),
            )

        assert result.imported == 1
        knowledge = [row for row in rows if row["kind"] == "knowledge"]
        assert len(knowledge) == 2
        by_path = {str(row["source_path"]): row for row in knowledge}
        runbook = by_path[f"{KNOWLEDGE_ROOT_A}/guides/runbook.md"]
        oncall = by_path[f"{KNOWLEDGE_ROOT_B}/team/oncall.md"]
        assert runbook["document_id"] == knowledge_document_id(
            f"{KNOWLEDGE_ROOT_A}/guides/runbook.md",
            KNOWLEDGE_ROOT_A,
        )
        assert runbook["document_revision"].startswith("digest:")
        assert runbook["retrieval_kind"] == "file_read"
        assert runbook["retrieval_scope"] == KNOWLEDGE_ROOT_A
        normalized = definition_hash("Runbook\nbody\n")
        assert normalized is not None
        assert runbook["document_revision"] == f"digest:{normalized}"
        assert oncall["retrieval_scope"] == KNOWLEDGE_ROOT_B
        assert all(row["line_no"] > 0 for row in knowledge)
        assert all(row["triggered_at"] is not None for row in knowledge)
        assert source_version == 6
        assert not any(str(row["source_path"]).startswith(SOURCE_ROOT) for row in rows)
    finally:
        await database.dispose()


async def test_root_without_any_bad_case_gets_no_knowledge_roots(tmp_path: Path) -> None:
    """An unreported local root has no workspace evidence, so no knowledge event."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_payload(database)

        await replay_pending_payloads(database)

        async with database.session() as session:
            rows = (await session.execute(select(agent_events))).mappings().all()
        assert rows == []
    finally:
        await database.dispose()


async def test_stale_parser_version_replays_an_already_processed_payload(
    tmp_path: Path,
) -> None:
    """A payload cursor pinned at parser 4 is stale and is rebuilt with knowledge rows."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_payload(database)
        await seed_workspace(
            database,
            workspace_id=WORKSPACE_A,
            name="Knowledge A",
            knowledge_roots=[KNOWLEDGE_ROOT_A],
            bad_case_id="bc-knowledge-a",
        )
        async with database.transaction() as session:
            await session.execute(
                source_records.insert().values(
                    runtime_key="claude-code",
                    root_session_id=ROOT_ID,
                    agent_id=ROOT_ID,
                    kind="main",
                    source_type="script",
                    line_count=len(MAIN_CONTENT.splitlines()),
                    received_at=now_shanghai(),
                    processed_at=now_shanghai(),
                    processed_hash=hashlib.sha256(MAIN_CONTENT.encode()).hexdigest(),
                    parser_version=4,
                    last_sync_run_id=None,
                ),
            )

        result = await replay_pending_payloads(database)

        async with database.session() as session:
            kinds = {
                str(row["kind"])
                for row in (await session.execute(select(agent_events))).mappings().all()
            }
            source = (
                (
                    await session.execute(
                        select(source_records).where(source_records.c.root_session_id == ROOT_ID),
                    )
                )
                .mappings()
                .one()
            )
        assert result.imported == 1
        assert "knowledge" in kinds
        assert source["parser_version"] == 6
    finally:
        await database.dispose()


async def test_replay_unions_more_than_twenty_roots_across_workspaces(
    tmp_path: Path,
) -> None:
    """Two workspaces with eleven roots each exceed the write-side limit, not replay."""
    roots_a = [f"/kb-a/{index}" for index in range(11)]
    roots_b = [f"/kb-b/{index}" for index in range(11)]
    content = jsonl(
        user(),
        read_call("tool-read", "/kb-b/10/guide.md"),
        read_result("tool-read", "/kb-b/10/guide.md", "body\n"),
    )
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_payload(database, content)
        await seed_workspace(
            database,
            workspace_id=WORKSPACE_A,
            name="Knowledge A",
            knowledge_roots=roots_a,
            bad_case_id="bc-knowledge-a",
        )
        await seed_workspace(
            database,
            workspace_id=WORKSPACE_B,
            name="Knowledge B",
            knowledge_roots=roots_b,
            bad_case_id="bc-knowledge-b",
        )

        result = await replay_pending_payloads(database)

        async with database.session() as session:
            rows = (await session.execute(select(agent_events))).mappings().all()
        knowledge = [row for row in rows if row["kind"] == "knowledge"]
        assert result.failed == 0
        assert result.imported == 1
        assert len(knowledge) == 1
        assert knowledge[0]["retrieval_scope"] == "/kb-b/10"
        assert knowledge[0]["source_path"] == "/kb-b/10/guide.md"
    finally:
        await database.dispose()


async def test_replay_survives_a_missing_bad_cases_table(tmp_path: Path) -> None:
    """An internal-only schema degrades to empty roots instead of failing the root."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        await seed_payload(database)
        async with database.transaction() as session:
            await session.execute(text("DROP TABLE bad_cases"))

        result = await replay_pending_payloads(database)

        async with database.session() as session:
            rows = (await session.execute(select(agent_events))).mappings().all()
            parser_version: int = int(
                (
                    await session.execute(
                        select(source_records.c.parser_version).where(
                            source_records.c.root_session_id == ROOT_ID,
                        ),
                    )
                ).scalar_one(),
            )
        assert result.failed == 0
        assert result.imported == 1
        assert rows == []
        assert parser_version == 6
    finally:
        await database.dispose()


async def test_a_304_character_root_round_trips_through_the_session_tree(
    tmp_path: Path,
) -> None:
    """A root within the 512 config limit is stored and returned unchanged."""
    long_root = "/" + "k" * 303
    assert len(long_root) == 304
    content = jsonl(
        user(),
        read_call("tool-read", f"{long_root}/guides/runbook.md"),
        read_result("tool-read", f"{long_root}/guides/runbook.md", "body\n"),
    )
    settings = settings_for(tmp_path)
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        await seed_payload(database, content)
        await seed_workspace(
            database,
            workspace_id=WORKSPACE_A,
            name="Knowledge A",
            knowledge_roots=[long_root],
            bad_case_id="bc-knowledge-a",
        )
        await replay_pending_payloads(database)
    finally:
        await database.dispose()

    events = await session_tree_events(settings)

    knowledge = [event for event in events if event["kind"] == "knowledge"]
    assert len(knowledge) == 1
    assert knowledge[0]["retrievalScope"] == long_root
    assert knowledge[0]["sourcePath"] == f"{long_root}/guides/runbook.md"


async def session_tree_events(settings: Settings) -> list[dict[str, object]]:
    """Query the Session tree as a global administrator and flatten its events."""
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "initial-password"},
        )
        token = login.json()["accessToken"]
        changed = await client.post(
            "/api/auth/change-password",
            headers=bearer(token),
            json={"oldPassword": "initial-password", "newPassword": "replacement-password"},
        )
        assert changed.status_code == 204
        authenticated = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "replacement-password"},
        )
        detail = await client.get(
            f"/api/sessions/{ROOT_ID}/tree",
            headers=bearer(authenticated.json()["accessToken"]),
        )
    assert detail.status_code == 200
    return [event for agent in detail.json()["agents"] for event in agent["events"]]


async def test_session_tree_api_exposes_knowledge_document_evidence(tmp_path: Path) -> None:
    """The Session tree DTO carries the document identity and coordinates."""
    settings = settings_for(tmp_path)
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        await seed_payload(database)
        await seed_workspace(
            database,
            workspace_id=WORKSPACE_A,
            name="Knowledge A",
            knowledge_roots=[KNOWLEDGE_ROOT_A],
            bad_case_id="bc-knowledge-a",
        )
        await replay_pending_payloads(database)
    finally:
        await database.dispose()

    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "initial-password"},
        )
        token = login.json()["accessToken"]
        changed = await client.post(
            "/api/auth/change-password",
            headers=bearer(token),
            json={"oldPassword": "initial-password", "newPassword": "replacement-password"},
        )
        assert changed.status_code == 204
        authenticated = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "replacement-password"},
        )
        headers = bearer(authenticated.json()["accessToken"])

        detail = await client.get(f"/api/sessions/{ROOT_ID}/tree", headers=headers)

    assert detail.status_code == 200
    events = [event for agent in detail.json()["agents"] for event in agent["events"]]
    knowledge = [event for event in events if event["kind"] == "knowledge"]
    assert len(knowledge) == 1
    event = knowledge[0]
    assert event["documentId"] == knowledge_document_id(
        f"{KNOWLEDGE_ROOT_A}/guides/runbook.md",
        KNOWLEDGE_ROOT_A,
    )
    assert event["documentRevision"].startswith("digest:")
    assert event["sourcePath"] == f"{KNOWLEDGE_ROOT_A}/guides/runbook.md"
    assert event["retrievalKind"] == "file_read"
    assert event["retrievalScope"] == KNOWLEDGE_ROOT_A
    assert event["line"] == 2
    assert "documentContent" not in event
