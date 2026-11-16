"""Revision 0019 knowledge columns, index, and workspace configuration defaults."""

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

ROOT_ID = "92000000-0000-4000-8000-000000000001"
WORKSPACE_ID = "ws-knowledge-legacy"
NOW = datetime(2026, 11, 16, 10, tzinfo=UTC)

KNOWLEDGE_COLUMNS = {
    "document_id",
    "document_revision",
    "source_path",
    "retrieval_kind",
    "retrieval_scope",
}


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database target."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'knowledge-migration.db'}",
    )


def alembic_config(database: Database) -> Config:
    """Build an Alembic config for explicit revision-path migration tests."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    return config


async def insert_pre_knowledge_rows(database: Database) -> None:
    """Write a pre-0019 Session, Agent, event, and workspace row."""
    async with database.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO source_records ("
                "runtime_key, root_session_id, agent_id, kind, source_type, line_count, "
                "received_at, processed_at, processed_hash, parser_version, last_sync_run_id"
                ") VALUES ("
                "'claude-code', :root_id, :root_id, 'main', 'script', 1, "
                ":now, :now, :hash, 4, NULL"
                ")",
            ),
            {"root_id": ROOT_ID, "now": NOW, "hash": "b" * 64},
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
                "sort_key, tree_index"
                ") VALUES ("
                ":root_id, 'claude-code', :root_id, NULL, 'main', 'sonnet', 0, 1, 0, 0, 0, 0, "
                "0, 0"
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
        await session.execute(
            text(
                "INSERT INTO workspaces (id, name, mark, quota, status, created_at, updated_at) "
                "VALUES (:workspace_id, 'Knowledge legacy', 'KL', 10, 'active', :now, :now)",
            ),
            {"workspace_id": WORKSPACE_ID, "now": NOW},
        )


async def test_knowledge_migration_adds_columns_index_and_workspace_default(
    tmp_path: Path,
) -> None:
    """Legacy rows keep NULL knowledge evidence and an empty root list."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0018")
        await insert_pre_knowledge_rows(database)

        await upgrade_database(database)
        await upgrade_database(database)

        async with database.session() as session:
            revision = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )
            event = (
                (
                    await session.execute(
                        text(
                            "SELECT document_id, document_revision, source_path, "
                            "retrieval_kind, retrieval_scope FROM agent_events "
                            "WHERE agent_id = :root_id",
                        ),
                        {"root_id": ROOT_ID},
                    )
                )
                .mappings()
                .one()
            )
            roots: object = (
                await session.execute(
                    text("SELECT knowledge_roots FROM workspaces WHERE id = :workspace_id"),
                    {"workspace_id": WORKSPACE_ID},
                )
            ).scalar_one()

        assert revision == "0020"
        assert dict(event) == {
            "document_id": None,
            "document_revision": None,
            "source_path": None,
            "retrieval_kind": None,
            "retrieval_scope": None,
        }
        assert roots is None

        async with database.engine.connect() as connection:
            columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns("agent_events")
                },
            )
            indexes = await connection.run_sync(
                lambda sync_connection: {
                    index["name"] for index in inspect(sync_connection).get_indexes("agent_events")
                },
            )
        assert columns >= KNOWLEDGE_COLUMNS
        assert "ix_agent_events_knowledge_document" in indexes
        async with database.engine.connect() as connection:
            scope_type = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]: column
                    for column in inspect(sync_connection).get_columns("agent_events")
                }["retrieval_scope"]["type"],
            )
        assert cast(String, scope_type).length == 512
    finally:
        await database.dispose()


async def test_knowledge_migration_resumes_after_partial_ddl(tmp_path: Path) -> None:
    """A retry after a half-applied DDL attempt adds only what is missing."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0018")
        await insert_pre_knowledge_rows(database)
        async with database.transaction() as session:
            await session.execute(
                text("ALTER TABLE agent_events ADD COLUMN document_id VARCHAR(255)"),
            )
            await session.execute(
                text("ALTER TABLE workspaces ADD COLUMN knowledge_roots JSON"),
            )

        await upgrade_database(database)

        async with database.engine.connect() as connection:
            columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns("agent_events")
                },
            )
        assert columns >= KNOWLEDGE_COLUMNS
    finally:
        await database.dispose()


async def test_knowledge_migration_rejects_wrong_existing_column(tmp_path: Path) -> None:
    """An out-of-band required knowledge column fails loudly instead of 500ing later."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0018")
        await insert_pre_knowledge_rows(database)
        async with database.transaction() as session:
            await session.execute(
                text(
                    "ALTER TABLE workspaces ADD COLUMN knowledge_roots JSON NOT NULL DEFAULT '[]'",
                ),
            )

        with pytest.raises(RuntimeError, match=r"workspaces\.knowledge_roots"):
            await upgrade_database(database)
    finally:
        await database.dispose()


async def test_knowledge_migration_downgrade_removes_columns_and_index(
    tmp_path: Path,
) -> None:
    """Downgrading to 0018 removes only the knowledge columns and index."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)

        await asyncio.to_thread(command.downgrade, alembic_config(database), "0018")

        async with database.engine.connect() as connection:
            event_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]
                    for column in inspect(sync_connection).get_columns("agent_events")
                },
            )
            workspace_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"] for column in inspect(sync_connection).get_columns("workspaces")
                },
            )
            indexes = await connection.run_sync(
                lambda sync_connection: {
                    index["name"] for index in inspect(sync_connection).get_indexes("agent_events")
                },
            )
        async with database.engine.connect() as connection:
            unique_constraints = await connection.run_sync(
                lambda sync_connection: {
                    constraint["name"]
                    for constraint in inspect(sync_connection).get_unique_constraints(
                        "agent_events",
                    )
                },
            )
        assert not KNOWLEDGE_COLUMNS & event_columns
        assert "knowledge_roots" not in workspace_columns
        assert "ix_agent_events_knowledge_document" not in indexes
        assert "uq_agent_events_agent_index" in unique_constraints
    finally:
        await database.dispose()
