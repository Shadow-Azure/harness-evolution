"""Alembic upgrade creates the service-owned catalog sync state table."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import inspect, text

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database

EXPECTED_COLUMNS = {
    "id",
    "last_bad_case_id",
    "synced_count",
    "pending_count",
    "assigned_count",
    "unassigned_count",
    "invalid_label_count",
    "status",
    "attempts",
    "last_error",
    "last_run_at",
    "last_success_at",
    "updated_at",
}


@pytest.mark.asyncio
async def test_upgrade_creates_catalog_sync_table(tmp_path: Path) -> None:
    """Head migration exposes the single-row cursor table with its primary key."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("catalog-sync-migration-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)

        async with database.engine.connect() as connection:
            exists, columns, primary_key = await connection.run_sync(
                lambda sync_connection: (
                    inspect(sync_connection).has_table("bad_case_catalog_sync"),
                    {
                        column["name"]
                        for column in inspect(sync_connection).get_columns(
                            "bad_case_catalog_sync",
                        )
                    },
                    inspect(sync_connection).get_pk_constraint("bad_case_catalog_sync")[
                        "constrained_columns"
                    ],
                ),
            )
        async with database.session() as session:
            revision: str = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )

        assert exists is True
        assert columns == EXPECTED_COLUMNS
        assert primary_key == ["id"]
        assert revision == "0033"
    finally:
        await database.dispose()


def _alembic_config(database: Database) -> Config:
    """Build a config for exercising the 0032 → head data migration."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    config.attributes["bootstrap_external_tables"] = True
    return config


@pytest.mark.asyncio
async def test_upgrade_backfills_workspace_bad_case_assignments(tmp_path: Path) -> None:
    """Legacy rows keep their owner; report rows become direct-ingest associations."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("workspace-assignment-migration-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, _alembic_config(database), "0032")
        async with database.session() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO bad_cases (
                      bad_case_id, workspace_id, origin, bad_case_session_id, bad_case_type,
                      object_name, object_type, title, bad_case_description, meta_data,
                      created_at, updated_at
                    ) VALUES
                      ('legacy-case', 'ws-default', 'catalog', 'session-1', 'skill',
                       'review', 'skill', 'Legacy', 'Legacy case', NULL,
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                      ('report-case', 'ws-default', 'report', 'session-2', 'skill',
                       'review', 'skill', 'Report', 'Reported case', NULL,
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                      ('catalog-labeled', 'ws-default', 'catalog', 'session-3', 'skill',
                       'review', 'skill', 'Labeled', 'Catalog case', '{"label": "code-review"}',
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                      ('catalog-invalid', 'ws-default', 'catalog', 'session-4', 'skill',
                       'review', 'skill', 'Invalid', 'Bad label', '{"label": "  spaced  "}',
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                ),
            )
            await session.commit()

        await upgrade_database(database)

        async with database.engine.connect() as connection:
            schema = await connection.run_sync(
                lambda sync_connection: {
                    "bad_case_columns": {
                        str(column["name"])
                        for column in inspect(sync_connection).get_columns("bad_cases")
                    },
                    "label_columns": {
                        str(column["name"])
                        for column in inspect(sync_connection).get_columns(
                            "workspace_bad_case_labels",
                        )
                    },
                    "assignment_columns": {
                        str(column["name"])
                        for column in inspect(sync_connection).get_columns(
                            "workspace_bad_cases",
                        )
                    },
                    "assignment_pk": inspect(sync_connection).get_pk_constraint(
                        "workspace_bad_cases",
                    )["constrained_columns"],
                    "assignment_fks": {
                        tuple(foreign_key["constrained_columns"])
                        for foreign_key in inspect(sync_connection).get_foreign_keys(
                            "workspace_bad_cases",
                        )
                    },
                    "bad_case_indexes": {
                        index["name"] for index in inspect(sync_connection).get_indexes("bad_cases")
                    },
                },
            )
        async with database.session() as session:
            cases = (
                await session.execute(
                    text(
                        "SELECT bad_case_id, catalog_label, catalog_synced "
                        "FROM bad_cases ORDER BY bad_case_id",
                    ),
                )
            ).all()
            assignments = (
                await session.execute(
                    text(
                        "SELECT bad_case_id, assignment_source "
                        "FROM workspace_bad_cases ORDER BY bad_case_id",
                    ),
                )
            ).all()

        assert "catalog_label" in schema["bad_case_columns"]
        assert "catalog_synced" in schema["bad_case_columns"]
        assert schema["label_columns"] == {
            "workspace_id",
            "label",
            "created_at",
            "updated_at",
        }
        assert schema["assignment_columns"] == {
            "workspace_id",
            "bad_case_id",
            "assignment_source",
            "label",
            "assigned_at",
        }
        assert schema["assignment_pk"] == [
            "workspace_id",
            "bad_case_id",
            "assignment_source",
        ]
        assert schema["assignment_fks"] == {("workspace_id",), ("bad_case_id",)}
        assert "ix_bad_cases_catalog_label" in schema["bad_case_indexes"]
        assert "ix_bad_cases_catalog_synced" in schema["bad_case_indexes"]
        assert [tuple(row) for row in cases] == [
            ("catalog-invalid", None, 1),
            ("catalog-labeled", "code-review", 1),
            ("legacy-case", None, 1),
            ("report-case", None, 0),
        ]
        assert [tuple(row) for row in assignments] == [
            ("catalog-invalid", "legacy_owner"),
            ("catalog-labeled", "legacy_owner"),
            ("legacy-case", "legacy_owner"),
            ("report-case", "direct_ingest"),
        ]
    finally:
        await database.dispose()
