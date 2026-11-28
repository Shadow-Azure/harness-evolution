"""Revision 0020 multi-attribution, cache, and candidate schema contracts."""

from __future__ import annotations

import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.attributions import attribution_cache_key
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.utils.time import SHANGHAI

NOW = datetime(2026, 11, 17, 9, tzinfo=SHANGHAI)
LATER = datetime(2026, 11, 17, 10, tzinfo=SHANGHAI)
WORKSPACE_ID = "ws-attribution-legacy"
DEFAULT_WORKSPACE_ID = "ws-default"

ISSUE_CASE_ID = "bc-legacy-issue"
NONISSUE_CASE_ID = "bc-legacy-nonissue"
PENDING_CASE_ID = "bc-legacy-pending"
ISSUE_PROBE_ID = "probe-legacy-issue"
NONISSUE_PROBE_ID = "probe-legacy-nonissue"
BLANK_PROBE_ID = "probe-legacy-blank"
ORPHAN_PROBE_ID = "probe-legacy-orphan"

PROBE_ADDED_COLUMNS = {
    "workspace_id",
    "conclusion",
    "confidence",
    "policy_version",
    "attribution_engine",
    "cache_key",
    "created_run_id",
    "last_reused_run_id",
    "reused_count",
}

CANDIDATE_COLUMNS = {
    "id",
    "run_id",
    "workspace_id",
    "session_id",
    "bad_case_id",
    "object_trigger_agent_id",
    "object_trigger_event_index",
    "object_trigger_at",
    "object_type",
    "object_name",
    "object_revision",
    "case_trigger_agent_id",
    "case_trigger_event_index",
    "case_anchor_kind",
    "case_trigger_at",
    "order_state",
    "included",
    "included_reason",
    "source_evidence",
    "probe_id",
    "is_cached",
    "created_at",
}


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite database target."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'attribution-migration.db'}",
    )


def alembic_config(database: Database) -> Config:
    """Build an Alembic config for explicit revision-path migration tests."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    return config


async def insert_pre_attribution_rows(database: Database) -> None:
    """Write V1 workspace, cases, probes, and analyses before revision 0020."""
    async with database.transaction() as session:
        await session.execute(
            text(
                "INSERT INTO workspaces (id, name, mark, quota, status, created_at, updated_at) "
                "VALUES (:workspace_id, '归因旧空间', 'A', 10, 'active', :now, :now)",
            ),
            {"workspace_id": WORKSPACE_ID, "now": NOW},
        )
        for case_id, session_id, case_type in (
            (ISSUE_CASE_ID, "session-issue", "self"),
            (NONISSUE_CASE_ID, "session-nonissue", "discovery"),
            (PENDING_CASE_ID, "session-pending", "self"),
        ):
            await session.execute(
                text(
                    "INSERT INTO bad_cases ("
                    "bad_case_id, workspace_id, bad_case_session_id, bad_case_type, "
                    "object_name, object_type, object_version, bad_case_agent_id, title, "
                    "bad_case_description, meta_data, source, created_at, updated_at"
                    ") VALUES ("
                    ":case_id, :workspace_id, :session_id, :case_type, "
                    "'deep-research', 'skill', 'v2.0.0', NULL, :case_id, 'legacy reason', "
                    "NULL, 'fixtures', :now, :now"
                    ")",
                ),
                {
                    "case_id": case_id,
                    "workspace_id": WORKSPACE_ID,
                    "session_id": session_id,
                    "case_type": case_type,
                    "now": NOW,
                },
            )
        for probe_id, session_id, probe_type, probe_object, version, attribute_type in (
            (ISSUE_PROBE_ID, "session-issue", "skill", "deep-research", "v2.0.0", "error"),
            (NONISSUE_PROBE_ID, "session-nonissue", "agent", "planner", None, "nonissue"),
            (BLANK_PROBE_ID, "session-pending", "skill", "deep-research", "v2.0.0", ""),
            (ORPHAN_PROBE_ID, "session-orphan", "skill", "orphan-skill", "v0.1.0", "prompt"),
        ):
            await session.execute(
                text(
                    "INSERT INTO probe_reports ("
                    "probe_id, session_id, probe_type, probe_object, object_version, "
                    "attribute_type, probe_description, probe_analysis, created_at, updated_at"
                    ") VALUES ("
                    ":probe_id, :session_id, :probe_type, :probe_object, :version, "
                    ":attribute_type, 'legacy description', 'legacy analysis', :now, :now"
                    ")",
                ),
                {
                    "probe_id": probe_id,
                    "session_id": session_id,
                    "probe_type": probe_type,
                    "probe_object": probe_object,
                    "version": version,
                    "attribute_type": attribute_type,
                    "now": NOW,
                },
            )
        await session.execute(
            text(
                "INSERT INTO bad_case_analysis ("
                "bad_case_id, analysis_status, probe_id, analysis_result, updated_at"
                ") VALUES "
                "(:issue_case, 'analyzed_issue', :issue_probe, '{\"summary\": \"legacy\"}', :now), "
                "(:nonissue_case, 'analyzed_nonissue', :nonissue_probe, NULL, :now), "
                "(:pending_case, 'unanalyzed', NULL, NULL, :now)",
            ),
            {
                "issue_case": ISSUE_CASE_ID,
                "issue_probe": ISSUE_PROBE_ID,
                "nonissue_case": NONISSUE_CASE_ID,
                "nonissue_probe": NONISSUE_PROBE_ID,
                "pending_case": PENDING_CASE_ID,
                "now": NOW,
            },
        )


async def probe_rows(database: Database) -> dict[str, dict[str, object]]:
    """Return every probe row keyed by probe id."""
    async with database.session() as session:
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT probe_id, workspace_id, conclusion, confidence, attribute_type, "
                        "policy_version, attribution_engine, cache_key, created_run_id, "
                        "last_reused_run_id, reused_count FROM probe_reports",
                    ),
                )
            )
            .mappings()
            .all()
        )
    return {str(row["probe_id"]): dict(row) for row in rows}


async def reflected(connection: AsyncConnection, table: str) -> dict[str, Any]:
    """Return columns, indexes, uniques, and foreign keys for one table."""

    def read(sync: Connection) -> dict[str, Any]:
        inspector = inspect(sync)
        return {
            "columns": {column["name"]: column for column in inspector.get_columns(table)},
            "indexes": {
                index["name"]: index
                for index in inspector.get_indexes(table)
                if index.get("name") is not None
            },
            "uniques": {
                constraint["name"]: constraint
                for constraint in inspector.get_unique_constraints(table)
                if constraint.get("name") is not None
            },
            "foreign_keys": {
                foreign_key["name"]: foreign_key
                for foreign_key in inspector.get_foreign_keys(table)
                if foreign_key.get("name") is not None
            },
        }

    return await connection.run_sync(read)


async def test_attribution_migration_backfills_legacy_rows_and_evolves_schema(
    tmp_path: Path,
) -> None:
    """Revision 0020 maps V1 rows, drops the case unique rule, and adds candidates."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0019")
        await insert_pre_attribution_rows(database)

        await upgrade_database(database)
        rows = await probe_rows(database)
        await upgrade_database(database)

        assert await probe_rows(database) == rows
        async with database.session() as session:
            revision = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )
            pending = (
                (
                    await session.execute(
                        text(
                            "SELECT bad_case_id, analysis_status, probe_id "
                            "FROM bad_case_analysis WHERE bad_case_id = :case_id",
                        ),
                        {"case_id": PENDING_CASE_ID},
                    )
                )
                .mappings()
                .one()
            )

        assert revision == "0038"
        assert dict(pending) == {
            "bad_case_id": PENDING_CASE_ID,
            "analysis_status": "unanalyzed",
            "probe_id": None,
        }

        issue = rows[ISSUE_PROBE_ID]
        assert issue["workspace_id"] == WORKSPACE_ID
        assert issue["conclusion"] == "attributed"
        assert issue["attribute_type"] == "error"
        assert issue["confidence"] == pytest.approx(0.8)
        assert issue["policy_version"] == "v1"
        assert issue["attribution_engine"] == "legacy-probe-import"
        assert issue["cache_key"] == attribution_cache_key(
            WORKSPACE_ID,
            ISSUE_CASE_ID,
            "skill",
            "deep-research",
            "v2.0.0",
            "v1",
            "legacy-probe-import",
        )
        assert issue["created_run_id"] is None
        assert issue["last_reused_run_id"] is None
        assert issue["reused_count"] == 0

        nonissue = rows[NONISSUE_PROBE_ID]
        assert nonissue["conclusion"] == "non_target"
        assert nonissue["attribute_type"] is None
        assert nonissue["cache_key"] == attribution_cache_key(
            WORKSPACE_ID,
            NONISSUE_CASE_ID,
            "agent",
            "planner",
            None,
            "v1",
            "legacy-probe-import",
        )

        assert rows[BLANK_PROBE_ID]["attribute_type"] is None
        assert rows[BLANK_PROBE_ID]["conclusion"] == "attributed"

        orphan = rows[ORPHAN_PROBE_ID]
        assert orphan["workspace_id"] == DEFAULT_WORKSPACE_ID
        assert orphan["conclusion"] == "attributed"
        assert orphan["cache_key"] is None

        async with database.engine.connect() as connection:
            probe_schema = await reflected(connection, "probe_reports")
            analysis_schema = await reflected(connection, "bad_case_analysis")
            candidate_schema = await reflected(connection, "evolution_run_candidates")

        assert set(probe_schema["columns"]) >= PROBE_ADDED_COLUMNS
        assert probe_schema["columns"]["attribute_type"]["nullable"] is True
        assert "DOUBLE" in str(probe_schema["columns"]["confidence"]["type"]).upper()
        assert probe_schema["columns"]["cache_key"]["nullable"] is True
        assert probe_schema["columns"]["object_version"]["nullable"] is True
        assert not probe_schema["columns"]["workspace_id"]["nullable"]
        assert {
            "uq_probe_reports_cache_key",
            "ix_probe_reports_workspace_object",
            "ix_probe_reports_workspace_updated",
            "ix_probe_reports_conclusion",
        } <= set(probe_schema["indexes"])
        assert probe_schema["indexes"]["uq_probe_reports_cache_key"]["unique"] == 1
        assert {
            "fk_probe_reports_workspace",
            "fk_probe_reports_created_run",
            "fk_probe_reports_last_reused_run",
        } <= set(probe_schema["foreign_keys"])

        assert analysis_schema["columns"]["analysis_status"]["nullable"] is True
        assert "uq_bad_case_analysis_case" not in analysis_schema["uniques"]
        assert "uq_bad_case_analysis_case_probe" in analysis_schema["uniques"]
        assert "ix_bad_case_analysis_case_updated" in analysis_schema["indexes"]

        assert set(candidate_schema["columns"]) == CANDIDATE_COLUMNS
        assert "uq_evolution_run_candidates_run_case" in candidate_schema["uniques"]
        assert {
            "ix_evolution_run_candidates_run_included",
            "ix_evolution_run_candidates_case",
            "ix_evolution_run_candidates_probe",
            "ix_evolution_run_candidates_session",
        } <= set(candidate_schema["indexes"])
        assert {
            "fk_evolution_run_candidates_run",
            "fk_evolution_run_candidates_workspace",
            "fk_evolution_run_candidates_case",
            "fk_evolution_run_candidates_probe",
        } <= set(candidate_schema["foreign_keys"])
    finally:
        await database.dispose()


async def test_attribution_migration_resumes_after_partial_ddl(tmp_path: Path) -> None:
    """A retry after a half-applied DDL attempt adds only what is missing."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0019")
        await insert_pre_attribution_rows(database)
        async with database.transaction() as session:
            await session.execute(
                text(
                    "ALTER TABLE probe_reports ADD COLUMN workspace_id VARCHAR(36) "
                    "NOT NULL DEFAULT 'ws-default'",
                ),
            )
            await session.execute(
                text(
                    "ALTER TABLE probe_reports ADD COLUMN conclusion VARCHAR(16) "
                    "NOT NULL DEFAULT 'attributed'",
                ),
            )
            await session.execute(
                text("ALTER TABLE probe_reports ADD COLUMN cache_key CHAR(64)"),
            )
            await session.execute(
                text(
                    "CREATE UNIQUE INDEX uq_probe_reports_cache_key ON probe_reports (cache_key)",
                ),
            )

        await upgrade_database(database)

        rows = await probe_rows(database)
        assert rows[ISSUE_PROBE_ID]["workspace_id"] == WORKSPACE_ID
        assert rows[ISSUE_PROBE_ID]["cache_key"] is not None
        assert rows[NONISSUE_PROBE_ID]["conclusion"] == "non_target"
        async with database.engine.connect() as connection:
            probe_schema = await reflected(connection, "probe_reports")
            candidate_schema = await reflected(connection, "evolution_run_candidates")
        assert set(probe_schema["columns"]) >= PROBE_ADDED_COLUMNS
        assert set(candidate_schema["columns"]) == CANDIDATE_COLUMNS
    finally:
        await database.dispose()


async def test_attribution_migration_rejects_wrong_existing_column(tmp_path: Path) -> None:
    """An out-of-band column with the wrong nullability fails loudly."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0019")
        await insert_pre_attribution_rows(database)
        async with database.transaction() as session:
            await session.execute(
                text(
                    "ALTER TABLE probe_reports ADD COLUMN cache_key CHAR(64) NOT NULL DEFAULT 'x'",
                ),
            )

        with pytest.raises(RuntimeError, match=r"probe_reports\.cache_key"):
            await upgrade_database(database)
    finally:
        await database.dispose()


async def test_attribution_migration_downgrade_restores_v1_shape(tmp_path: Path) -> None:
    """Downgrade keeps one latest attribution per case and restores V1 columns."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        async with database.transaction() as session:
            await session.execute(
                text(
                    "INSERT INTO bad_cases ("
                    "bad_case_id, workspace_id, bad_case_session_id, bad_case_type, "
                    "object_name, object_type, object_version, bad_case_agent_id, title, "
                    "bad_case_description, meta_data, source, created_at, updated_at"
                    ") VALUES ("
                    "'bc-downgrade', 'ws-default', 'session-down', 'self', "
                    "'deep-research', 'skill', 'v1.0.0', NULL, 'bc-downgrade', 'reason', "
                    "NULL, 'fixtures', :now, :now"
                    ")",
                ),
                {"now": NOW},
            )
            for probe_id, updated_at in (("probe-old", NOW), ("probe-new", LATER)):
                await session.execute(
                    text(
                        "INSERT INTO probe_reports ("
                        "probe_id, workspace_id, session_id, probe_type, probe_object, "
                        "object_version, attribute_type, conclusion, confidence, "
                        "probe_description, probe_analysis, policy_version, "
                        "attribution_engine, cache_key, created_run_id, last_reused_run_id, "
                        "reused_count, created_at, updated_at"
                        ") VALUES ("
                        ":probe_id, 'ws-default', 'session-down', 'skill', 'deep-research', "
                        "'v1.0.0', NULL, 'non_target', 0.5, 'description', 'analysis', 'v1', "
                        "'engine', :cache_key, NULL, NULL, 0, :now, :updated_at"
                        ")",
                    ),
                    {
                        "probe_id": probe_id,
                        "cache_key": "a" * 64 if probe_id == "probe-old" else "b" * 64,
                        "now": NOW,
                        "updated_at": updated_at,
                    },
                )
            await session.execute(
                text(
                    "INSERT INTO bad_case_analysis ("
                    "bad_case_id, analysis_status, probe_id, analysis_result, updated_at"
                    ") VALUES "
                    "('bc-downgrade', 'analyzed_issue', 'probe-old', NULL, :now), "
                    "('bc-downgrade', NULL, 'probe-new', NULL, :later)",
                ),
                {"now": NOW, "later": LATER},
            )

        await asyncio.to_thread(command.downgrade, alembic_config(database), "0019")

        async with database.session() as session:
            revision = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT bad_case_id, analysis_status, probe_id "
                            "FROM bad_case_analysis WHERE bad_case_id = 'bc-downgrade'",
                        ),
                    )
                )
                .mappings()
                .all()
            )
            probe = (
                (
                    await session.execute(
                        text(
                            "SELECT attribute_type FROM probe_reports WHERE probe_id = 'probe-new'",
                        ),
                    )
                )
                .mappings()
                .one()
            )
        assert revision == "0019"
        assert [dict(row) for row in rows] == [
            {
                "bad_case_id": "bc-downgrade",
                "analysis_status": "analyzed_nonissue",
                "probe_id": "probe-new",
            },
        ]
        assert probe["attribute_type"] == "nonissue"

        async with database.engine.connect() as connection:
            probe_schema = await reflected(connection, "probe_reports")
            analysis_schema = await reflected(connection, "bad_case_analysis")
            tables = await connection.run_sync(
                lambda sync: set(inspect(sync).get_table_names()),
            )
        assert not PROBE_ADDED_COLUMNS & set(probe_schema["columns"])
        assert not probe_schema["columns"]["attribute_type"]["nullable"]
        assert not {
            "uq_probe_reports_cache_key",
            "ix_probe_reports_workspace_object",
            "ix_probe_reports_workspace_updated",
            "ix_probe_reports_conclusion",
        } & set(probe_schema["indexes"])
        assert not analysis_schema["columns"]["analysis_status"]["nullable"]
        assert "uq_bad_case_analysis_case" in analysis_schema["uniques"]
        assert "uq_bad_case_analysis_case_probe" not in analysis_schema["uniques"]
        assert "evolution_run_candidates" not in tables

        await upgrade_database(database)
        async with database.session() as session:
            revision = str(
                (
                    await session.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one(),
            )
        assert revision == "0038"
    finally:
        await database.dispose()


async def test_attribution_migration_skips_missing_external_tables(tmp_path: Path) -> None:
    """The runtime upgrade still reaches head when external tables are absent."""
    database = create_database(settings_for(tmp_path))
    await database.start()
    try:
        await upgrade_database(database, bootstrap_external_tables=False)

        async with database.engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync: set(inspect(sync).get_table_names()),
            )
            candidate_schema = await reflected(connection, "evolution_run_candidates")
        assert {"bad_cases", "probe_reports", "bad_case_analysis"} & tables == set()
        assert set(candidate_schema["columns"]) == CANDIDATE_COLUMNS
        assert "fk_evolution_run_candidates_case" not in candidate_schema["foreign_keys"]
        assert "fk_evolution_run_candidates_probe" not in candidate_schema["foreign_keys"]
        assert "fk_evolution_run_candidates_run" in candidate_schema["foreign_keys"]
    finally:
        await database.dispose()


def load_migration_module() -> object:
    """Load revision 0020 as an importable module for a pure helper contract."""
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0020_v2_attribution_schema.py"
    )
    spec = importlib.util.spec_from_file_location("revision_0020", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cache_key_backfill_plan_skips_duplicate_and_orphan_rows() -> None:
    """Duplicate identities and orphan probes are counted, not silently dropped."""
    module = load_migration_module()
    rows = [
        {
            "probe_id": "probe-a",
            "workspace_id": WORKSPACE_ID,
            "probe_type": "skill",
            "probe_object": "deep-research",
            "object_version": "v2.0.0",
            "policy_version": "v1",
            "attribution_engine": "legacy-probe-import",
            "bad_case_id": ISSUE_CASE_ID,
        },
        {
            "probe_id": "probe-b",
            "workspace_id": WORKSPACE_ID,
            "probe_type": "skill",
            "probe_object": "deep-research",
            "object_version": "v2.0.0",
            "policy_version": "v1",
            "attribution_engine": "legacy-probe-import",
            "bad_case_id": ISSUE_CASE_ID,
        },
        {
            "probe_id": "probe-orphan",
            "workspace_id": DEFAULT_WORKSPACE_ID,
            "probe_type": "skill",
            "probe_object": "orphan",
            "object_version": None,
            "policy_version": "v1",
            "attribution_engine": "legacy-probe-import",
            "bad_case_id": None,
        },
    ]

    updates, skipped = module._cache_key_backfill_plan(rows, set())  # type: ignore[attr-defined]

    assert [probe_id for probe_id, _key in updates] == ["probe-a"]
    assert skipped == 2
    expected = attribution_cache_key(
        WORKSPACE_ID,
        ISSUE_CASE_ID,
        "skill",
        "deep-research",
        "v2.0.0",
        "v1",
        "legacy-probe-import",
    )
    assert updates[0][1] == expected

    retry_updates, retry_skipped = module._cache_key_backfill_plan(  # type: ignore[attr-defined]
        rows[1:],
        {expected},
    )
    assert retry_updates == []
    assert retry_skipped == 2
