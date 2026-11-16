"""Revision 0015 runtime backfill and composite identity contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import source_records, trajectory_payloads

ROOT_ID = "55555555-5555-4555-8555-555555555555"
NOW = datetime(2026, 10, 22, 1, tzinfo=UTC)


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database target."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'runtime-migration.db'}",
    )


def alembic_config(database: Database) -> Config:
    """Build an Alembic config for explicit revision-path migration tests."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    return config


async def insert_legacy_rows(database: Database) -> None:
    """Write one pre-0015 payload, cursor, and Session without runtime identity."""
    async with database.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO trajectory_payloads ("
                "root_session_id, agent_id, agent_kind, payload, agent_meta, "
                "content_hash, line_count, source_type, updated_at"
                ") VALUES ("
                ":root_id, :root_id, 'main', '{\"type\":\"user\"}', NULL, "
                ":content_hash, 1, 'script', :now"
                ")",
            ),
            {"root_id": ROOT_ID, "content_hash": "a" * 64, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO source_records ("
                "root_session_id, agent_id, kind, source_type, line_count, received_at, "
                "processed_at, processed_hash, parser_version, last_sync_run_id"
                ") VALUES ("
                ":root_id, :root_id, 'main', 'script', 1, :now, NULL, NULL, NULL, NULL"
                ")",
            ),
            {"root_id": ROOT_ID, "now": NOW},
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
                "id, short_title, title, search_text, repo_name, project_path, "
                "git_branch, cli_version, entrypoint, model, models, started_at, ended_at, "
                "duration_seconds, status, skill_names, user_turns_count, messages_count, "
                "tools_count, errors_count, agents_count, tokens_total, source_type, "
                "main_record_id, imported_at, updated_at"
                ") VALUES ("
                ":root_id, 'legacy', 'legacy', 'legacy', 'repo', '/workspace/repo', "
                "NULL, NULL, NULL, NULL, '[]', :now, :now, 0, 'ok', '[]', 0, 0, 0, 0, 0, 0, "
                "'script', :source_id, :now, :now"
                ")",
            ),
            {"root_id": ROOT_ID, "source_id": source_id, "now": NOW},
        )
        await session.execute(
            text(
                "INSERT INTO agents ("
                "id, root_session_id, parent_agent_id, kind, spawn_depth, lines, "
                "messages_count, tokens_total, tools_count, errors_count, sort_key"
                ") VALUES ("
                ":root_id, :root_id, NULL, 'main', 0, 1, 0, 0, 0, 0, 0"
                ")",
            ),
            {"root_id": ROOT_ID},
        )


async def test_runtime_migration_backfills_and_allows_per_runtime_identity(
    tmp_path: Path,
) -> None:
    """Legacy rows become Claude rows while the identity key gains runtime."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0014")
        await insert_legacy_rows(database)

        await upgrade_database(database)

        async with database.session() as session:
            payload_runtime: str = cast(
                str,
                (await session.execute(select(trajectory_payloads.c.runtime_key))).scalar_one(),
            )
            source_runtime: str = cast(
                str,
                (await session.execute(select(source_records.c.runtime_key))).scalar_one(),
            )
            family_runtime: str = cast(
                str,
                (
                    await session.execute(text("SELECT runtime_key FROM session_families"))
                ).scalar_one(),
            )
            agent_runtime: str = cast(
                str,
                (await session.execute(text("SELECT runtime_key FROM agents"))).scalar_one(),
            )
        assert payload_runtime == "claude-code"
        assert source_runtime == "claude-code"
        assert family_runtime == "claude-code"
        assert agent_runtime == "claude-code"

        async with database.engine.connect() as connection:
            payload_pk = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_pk_constraint(
                    "trajectory_payloads",
                ),
            )
            source_unique = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_unique_constraints(
                    "source_records",
                ),
            )
        assert payload_pk["constrained_columns"] == [
            "runtime_key",
            "root_session_id",
            "agent_id",
        ]
        assert any(
            constraint["column_names"] == ["runtime_key", "root_session_id", "agent_id"]
            for constraint in source_unique
        )

        async with database.transaction() as session:
            await session.execute(
                trajectory_payloads.insert().values(
                    runtime_key="fake-runtime",
                    root_session_id=ROOT_ID,
                    agent_id=ROOT_ID,
                    agent_kind="main",
                    payload="{}",
                    agent_meta=None,
                    content_hash="b" * 64,
                    line_count=1,
                    source_type="script",
                    updated_at=NOW,
                ),
            )
            await session.execute(
                source_records.insert().values(
                    runtime_key="fake-runtime",
                    root_session_id=ROOT_ID,
                    agent_id=ROOT_ID,
                    kind="main",
                    source_type="script",
                    line_count=1,
                    received_at=NOW,
                    processed_at=None,
                    processed_hash=None,
                    parser_version=None,
                    last_sync_run_id=None,
                ),
            )

        async with database.session() as session:
            payloads: list[str] = list(
                (
                    await session.execute(
                        select(trajectory_payloads.c.runtime_key).order_by(
                            trajectory_payloads.c.runtime_key,
                        ),
                    )
                )
                .scalars()
                .all(),
            )
            sources: list[str] = list(
                (
                    await session.execute(
                        select(source_records.c.runtime_key).order_by(
                            source_records.c.runtime_key,
                        ),
                    )
                )
                .scalars()
                .all(),
            )
        assert payloads == ["claude-code", "fake-runtime"]
        assert sources == ["claude-code", "fake-runtime"]

        with pytest.raises(IntegrityError):
            async with database.transaction() as session:
                await session.execute(
                    source_records.insert().values(
                        runtime_key="fake-runtime",
                        root_session_id=ROOT_ID,
                        agent_id=ROOT_ID,
                        kind="main",
                        source_type="script",
                        line_count=1,
                        received_at=NOW,
                    ),
                )
    finally:
        await database.dispose()
