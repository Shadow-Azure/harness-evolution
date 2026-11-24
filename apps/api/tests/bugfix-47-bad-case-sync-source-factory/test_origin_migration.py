"""Revision 0032: origin column and historic writer backfill."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.utils.time import now_shanghai


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'origin-migration.db'}",
        jwt_secret=SecretStr("origin-migration-test-secret"),
    )


def _alembic_config(database: Database) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    return config


async def _insert_case(
    database: Database,
    *,
    case_id: str,
    workspace_id: str,
    session_source: str | None,
) -> None:
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO bad_cases ("
                "bad_case_id, workspace_id, bad_case_session_id, bad_case_type, "
                "object_name, object_type, bad_case_agent_id, title, "
                "bad_case_description, meta_data, source, session_source, "
                "created_at, updated_at"
                ") VALUES ("
                ":bad_case_id, :workspace_id, :session_id, 'self', "
                "'deep-research', 'skill', NULL, 'case', "
                "'description', NULL, 'test', :session_source, "
                ":created_at, :updated_at"
                ")",
            ),
            {
                "bad_case_id": case_id,
                "workspace_id": workspace_id,
                "session_id": f"session-{case_id}",
                "session_source": session_source,
                "created_at": now,
                "updated_at": now,
            },
        )


@pytest.mark.asyncio
async def test_upgrade_backfills_report_and_catalog_origins(tmp_path: Path) -> None:
    """The backfill mirrors the two historic writer signatures."""
    database = create_database(_settings(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, _alembic_config(database), "0031")
        await _insert_case(
            database,
            case_id="default-no-source",
            workspace_id=DEFAULT_WORKSPACE_ID,
            session_source=None,
        )
        await _insert_case(
            database,
            case_id="other-workspace",
            workspace_id="ws-other",
            session_source=None,
        )
        await _insert_case(
            database,
            case_id="default-with-source",
            workspace_id=DEFAULT_WORKSPACE_ID,
            session_source='{"runtime": "claude-code", "sessionUrlTemplate": "https://x/{sessionId}"}',
        )

        await asyncio.to_thread(command.upgrade, _alembic_config(database), "head")

        async with database.session() as session:
            rows = (
                (
                    await session.execute(
                        text("SELECT bad_case_id, origin FROM bad_cases"),
                    )
                )
                .mappings()
                .all()
            )
            revision: str = str(
                (
                    await session.execute(
                        text("SELECT version_num FROM alembic_version"),
                    )
                ).scalar_one(),
            )

        origins = {str(row["bad_case_id"]): str(row["origin"]) for row in rows}
        assert revision == "0032"
        assert origins == {
            "default-no-source": "catalog",
            "other-workspace": "report",
            "default-with-source": "report",
        }
    finally:
        await database.dispose()
