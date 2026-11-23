"""Revision 0018 trigger-coordinate columns and legacy backfill contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alembic.config import Config
from sqlalchemy import inspect, text

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database

ROOT_ID = "77777777-7777-4777-8777-777777777777"
NOW = datetime(2026, 11, 16, 10, tzinfo=UTC)


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database target."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'trigger-coordinates.db'}",
    )


def alembic_config(database: Database) -> Config:
    """Build an Alembic config for explicit revision-path migration tests."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    return config


async def insert_legacy_coordinate_rows(database: Database) -> None:
    """Write a pre-0018 Session, Agent, event, and source cursor."""
    async with database.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO source_records ("
                "runtime_key, root_session_id, agent_id, kind, source_type, line_count, "
                "received_at, processed_at, processed_hash, parser_version, last_sync_run_id"
                ") VALUES ("
                "'claude-code', :root_id, :root_id, 'main', 'script', 1, "
                ":now, :now, :hash, 8, NULL"
                ")",
            ),
            {"root_id": ROOT_ID, "now": NOW, "hash": "a" * 64},
        )
        source_id: int = cast(
            int,
            (
                await session.execute(
                    text("SELECT id FROM source_records WHERE root_session_id = :root_id"),
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


async def test_coordinate_migration_defaults_legacy_rows_and_is_idempotent(
    tmp_path: Path,
) -> None:
    """Legacy Agents start at tree_index 0 while event coordinates stay NULL."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0017")
        await insert_legacy_coordinate_rows(database)

        await upgrade_database(database)
        await upgrade_database(database)

        async with database.session() as session:
            revision = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )
            agent = (
                (
                    await session.execute(
                        text(
                            "SELECT tree_index FROM agents WHERE id = :root_id",
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
                            "SELECT triggered_at, object_version, object_revision "
                            "FROM agent_events WHERE agent_id = :root_id",
                        ),
                        {"root_id": ROOT_ID},
                    )
                )
                .mappings()
                .one()
            )
        assert revision == "0031"
        assert agent["tree_index"] == 0
        assert event["triggered_at"] is None
        assert event["object_version"] is None
        assert event["object_revision"] is None
    finally:
        await database.dispose()


async def test_coordinate_migration_downgrade_removes_columns_and_indexes(
    tmp_path: Path,
) -> None:
    """Downgrading to 0017 removes only the coordinate columns and indexes."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)

        async with database.engine.connect() as connection:
            indexes = await connection.run_sync(
                lambda sync_connection: {
                    index["name"] for index in inspect(sync_connection).get_indexes("agent_events")
                },
            )
            assert "ix_agent_events_agent_triggered" in indexes
            assert "ix_agent_events_object_version" in indexes

        await asyncio.to_thread(command.downgrade, alembic_config(database), "0017")

        async with database.engine.connect() as connection:
            inspection = await connection.run_sync(
                lambda sync_connection: {
                    table: {
                        column["name"] for column in inspect(sync_connection).get_columns(table)
                    }
                    for table in ("agents", "agent_events")
                },
            )
            indexes = await connection.run_sync(
                lambda sync_connection: {
                    index["name"] for index in inspect(sync_connection).get_indexes("agent_events")
                },
            )
        assert "tree_index" not in inspection["agents"]
        assert "triggered_at" not in inspection["agent_events"]
        assert "object_version" not in inspection["agent_events"]
        assert "ix_agent_events_agent_triggered" not in indexes
        assert "ix_agent_events_object_version" not in indexes
    finally:
        await database.dispose()
