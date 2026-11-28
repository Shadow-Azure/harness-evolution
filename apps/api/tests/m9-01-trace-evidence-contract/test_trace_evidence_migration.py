"""Revision 0016 M9 evidence columns and legacy backfill contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from alembic.config import Config
from sqlalchemy import String, inspect, text

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database

ROOT_ID = "66666666-6666-4666-8666-666666666666"
NOW = datetime(2026, 11, 16, 10, tzinfo=UTC)


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database target."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'trace-evidence-migration.db'}",
    )


def alembic_config(database: Database) -> Config:
    """Build an Alembic config for explicit revision-path migration tests."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    return config


async def insert_legacy_evidence_rows(database: Database) -> None:
    """Write a pre-0016 Session, Agent, event, and processed source cursor."""
    async with database.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO source_records ("
                "runtime_key, root_session_id, agent_id, kind, source_type, line_count, "
                "received_at, processed_at, processed_hash, parser_version, last_sync_run_id"
                ") VALUES ("
                "'claude-code', :root_id, :root_id, 'main', 'script', 1, "
                ":now, :now, :hash, 7, NULL"
                ")",
            ),
            {"root_id": ROOT_ID, "now": NOW, "hash": "a" * 64},
        )
        source_id: int = cast(
            int,
            (
                await session.execute(
                    text(
                        "SELECT id FROM source_records WHERE root_session_id = :root_id",
                    ),
                    {"root_id": ROOT_ID},
                )
            ).scalar_one(),
        )
        await session.execute(
            text(
                "INSERT INTO session_families ("
                "id, runtime_key, short_title, title, search_text, repo_name, project_path, "
                "git_branch, cli_version, entrypoint, model, models, started_at, ended_at, "
                "duration_seconds, status, skill_names, user_turns_count, messages_count, "
                "tools_count, errors_count, agents_count, tokens_total, source_type, "
                "main_record_id, imported_at, updated_at"
                ") VALUES ("
                ":root_id, 'claude-code', 'legacy', 'legacy', 'legacy', 'repo', "
                "'/workspace/repo', NULL, '2.0.1', NULL, 'model-before', '[\"model-before\"]', "
                ":now, :now, 0, 'ok', '[]', 0, 0, 0, 0, 0, 0, 'script', :source_id, :now, :now"
                ")",
            ),
            {"root_id": ROOT_ID, "source_id": source_id, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO agents ("
                "id, runtime_key, root_session_id, parent_agent_id, kind, requested_model, "
                "spawn_depth, lines, messages_count, tokens_total, tools_count, errors_count, "
                "sort_key"
                ") VALUES ("
                ":root_id, 'claude-code', :root_id, NULL, 'main', 'sonnet', 0, 1, 0, 0, 0, 0, 0"
                ")",
            ),
            {"root_id": ROOT_ID},
        )
        await session.execute(
            text(
                "INSERT INTO agent_events ("
                "agent_id, event_index, line_no, message_offset, kind, name, description, "
                "tool_use_id"
                ") VALUES ("
                ":root_id, 0, 1, 0, 'skill', 'legacy-skill', 'legacy', 'tool-legacy'"
                ")",
            ),
            {"root_id": ROOT_ID},
        )


async def test_evidence_migration_defaults_legacy_states_and_keeps_runtime(
    tmp_path: Path,
) -> None:
    """Legacy rows read legacy_unknown while runtime and parser evidence survives."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0015")
        await insert_legacy_evidence_rows(database)

        await upgrade_database(database)
        await upgrade_database(database)

        async with database.session() as session:
            revision = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )
            family = (
                (
                    await session.execute(
                        text(
                            "SELECT execution_outcome, end_reason FROM session_families "
                            "WHERE id = :root_id",
                        ),
                        {"root_id": ROOT_ID},
                    )
                )
                .mappings()
                .one()
            )
            agent = (
                (
                    await session.execute(
                        text(
                            "SELECT execution_outcome, end_reason, agent_definition_hash, "
                            "definition_source FROM agents WHERE id = :root_id",
                        ),
                        {"root_id": ROOT_ID},
                    )
                )
                .mappings()
                .one()
            )
            event = (
                (
                    await session.execute(
                        text(
                            "SELECT object_revision, definition_hash, file_read_hash, "
                            "read_complete, relation_confidence FROM agent_events "
                            "WHERE agent_id = :root_id",
                        ),
                        {"root_id": ROOT_ID},
                    )
                )
                .mappings()
                .one()
            )
            source = (
                (
                    await session.execute(
                        text("SELECT runtime_key, parser_version FROM source_records"),
                    )
                )
                .mappings()
                .one()
            )

        assert revision == "0037"
        assert dict(family) == {
            "execution_outcome": "legacy_unknown",
            "end_reason": None,
        }
        assert dict(agent) == {
            "execution_outcome": "legacy_unknown",
            "end_reason": None,
            "agent_definition_hash": None,
            "definition_source": None,
        }
        assert dict(event) == {
            "object_revision": None,
            "definition_hash": None,
            "file_read_hash": None,
            "read_complete": None,
            "relation_confidence": None,
        }
        assert dict(source) == {"runtime_key": "claude-code", "parser_version": 7}

        async with database.engine.connect() as connection:
            reflected = await connection.run_sync(
                lambda sync_connection: {
                    table: {
                        column["name"]: column
                        for column in inspect(sync_connection).get_columns(table)
                    }
                    for table in ("session_families", "agents", "agent_events")
                },
            )
        assert reflected["session_families"]["execution_outcome"]["nullable"] is False
        assert reflected["session_families"]["end_reason"]["nullable"] is True
        assert reflected["agents"]["execution_outcome"]["nullable"] is False
        assert reflected["agents"]["end_reason"]["nullable"] is True
        assert cast(String, reflected["agents"]["agent_definition_hash"]["type"]).length == 64
        assert reflected["agents"]["definition_source"]["nullable"] is True
        assert cast(String, reflected["agent_events"]["object_revision"]["type"]).length == 96
        assert cast(String, reflected["agent_events"]["definition_hash"]["type"]).length == 64
        assert cast(String, reflected["agent_events"]["file_read_hash"]["type"]).length == 64
        assert reflected["agent_events"]["read_complete"]["nullable"] is True

        await asyncio.to_thread(command.downgrade, alembic_config(database), "0015")
        async with database.engine.connect() as connection:
            downgraded = await connection.run_sync(
                lambda sync_connection: {
                    table: {
                        column["name"] for column in inspect(sync_connection).get_columns(table)
                    }
                    for table in ("session_families", "agents", "agent_events")
                },
            )
        assert "execution_outcome" not in downgraded["session_families"]
        assert "end_reason" not in downgraded["agents"]
        assert "relation_confidence" not in downgraded["agent_events"]

        await upgrade_database(database)
        async with database.session() as session:
            outcome: str = (
                await session.execute(
                    text(
                        "SELECT execution_outcome FROM session_families WHERE id = :root_id",
                    ),
                    {"root_id": ROOT_ID},
                )
            ).scalar_one()
        assert outcome == "legacy_unknown"
    finally:
        await database.dispose()


async def test_evidence_migration_resumes_after_partial_ddl(tmp_path: Path) -> None:
    """A retry after a half-applied MySQL DDL attempt adds only what is missing."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0015")
        await insert_legacy_evidence_rows(database)
        async with database.transaction() as session:
            await session.execute(
                text("ALTER TABLE agents ADD COLUMN end_reason VARCHAR(32)"),
            )

        await upgrade_database(database)

        async with database.session() as session:
            revision = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )
            outcome: str = (
                await session.execute(
                    text(
                        "SELECT execution_outcome FROM agents WHERE id = :root_id",
                    ),
                    {"root_id": ROOT_ID},
                )
            ).scalar_one()
            relation: str | None = (
                await session.execute(
                    text(
                        "SELECT relation_confidence FROM agent_events WHERE agent_id = :root_id",
                    ),
                    {"root_id": ROOT_ID},
                )
            ).scalar_one()

        assert revision == "0037"
        assert outcome == "legacy_unknown"
        assert relation is None
        async with database.engine.connect() as connection:
            columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns("agent_events")
                },
            )
        assert {
            "object_revision",
            "definition_hash",
            "file_read_hash",
            "read_complete",
            "relation_confidence",
        } <= columns
    finally:
        await database.dispose()


async def test_evidence_migration_rejects_wrong_existing_definition(
    tmp_path: Path,
) -> None:
    """An out-of-band nullable execution_outcome fails loudly instead of 500ing later."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0015")
        await insert_legacy_evidence_rows(database)
        async with database.transaction() as session:
            await session.execute(
                text(
                    "ALTER TABLE session_families ADD COLUMN execution_outcome VARCHAR(16)",
                ),
            )

        with pytest.raises(RuntimeError, match=r"session_families\.execution_outcome"):
            await upgrade_database(database)
    finally:
        await database.dispose()
