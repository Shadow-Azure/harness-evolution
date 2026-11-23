"""Upgrade released and partially upgraded databases without losing attribution reports."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

V2_COLUMNS = {
    "report_schema_version",
    "report_payload",
    "execution_manifest",
    "execution_manifest_hash",
}


@pytest.mark.parametrize("revision", ["0022", "0023", "0026", "0028"])
def test_existing_database_reaches_head(tmp_path: Path, revision: str) -> None:
    """Released production heads and partially upgraded databases retain their reports."""
    path = tmp_path / "existing.db"
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{path}")
    config.attributes["configure_logger"] = False
    command.upgrade(config, revision)
    with closing(sqlite3.connect(path)) as conn:
        assert "trigger_line" in {row[1] for row in conn.execute("PRAGMA table_info(bad_cases)")}
        assert not V2_COLUMNS.intersection(
            row[1] for row in conn.execute("PRAGMA table_info(probe_reports)")
        )
        conn.execute(
            "INSERT INTO evolution_targets (id, object_type, object_name, repo_url, sub_dir, "
            "default_ref, created_at, updated_at) "
            "VALUES ('production-target', 'agent', 'existing', 'repo', 'agents', 'main', "
            "'2026-11-01', '2026-11-01')"
        )
        conn.execute(
            "INSERT INTO probe_reports "
            "(probe_id, session_id, probe_type, probe_object, probe_description, "
            " probe_analysis, created_at, updated_at) "
            "VALUES ('existing', 's', 'skill', 'x', 'description', 'prior analysis', "
            "        '2026-11-01', '2026-11-01')"
        )
        conn.commit()

    command.upgrade(config, "head")
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == (
            ScriptDirectory.from_config(config).get_current_head(),
        )
        assert {row[1] for row in conn.execute("PRAGMA table_info(probe_reports)")} >= V2_COLUMNS
        assert "ix_probe_reports_manifest_hash" in {
            row[1] for row in conn.execute("PRAGMA index_list(probe_reports)")
        }
        assert conn.execute(
            "SELECT attribution_package_id, attribution_generation, attribution_due "
            "FROM evolution_targets WHERE id = 'production-target'"
        ).fetchone() == (None, None, None)
        assert conn.execute(
            "SELECT probe_analysis, analyzed_at, attribution_skill_name FROM probe_reports "
            "WHERE probe_id = 'existing'"
        ).fetchone() == ("prior analysis", "2026-11-01", None)


def test_previous_attribution_head_acquires_production_schema(tmp_path: Path) -> None:
    """A PR 0030 database already owns its lease columns and attribution packages."""
    path = tmp_path / "legacy-attribution.db"
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{path}")
    config.attributes["configure_logger"] = False
    command.upgrade(config, "0030")
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("DROP INDEX ix_job_runs_status_lease_expires_at")
        conn.execute("CREATE INDEX ix_job_runs_lease_expiry ON job_runs(status, lease_expires_at)")
        conn.execute("ALTER TABLE job_runs DROP COLUMN heartbeat_at")
        conn.execute("ALTER TABLE evolution_runs DROP COLUMN push_repo_url")
        conn.execute("ALTER TABLE evolution_runs DROP COLUMN control_state")
        conn.execute("ALTER TABLE evolution_rounds DROP COLUMN eval_paused_seconds")
        conn.execute(
            "INSERT INTO job_runs(id, kind, status, progress, executor, attempt, payload, "
            "created_at, updated_at, lease_owner, max_attempts) VALUES "
            "('prior-batch', 'attribution_batch', 'running', .5, 'local', 2, '{}', "
            "'2026-11-21', '2026-11-21', 'prior-owner', 7)"
        )
        conn.commit()

    command.upgrade(config, "head")
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute(
            "SELECT lease_owner, attempt, max_attempts, progress, heartbeat_at FROM job_runs "
            "WHERE id = 'prior-batch'"
        ).fetchone() == ("prior-owner", 2, 7, 0.5, None)
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(job_runs)")}
        assert "ix_job_runs_status_lease_expires_at" in indexes
        assert "ix_job_runs_lease_expiry" not in indexes
        assert {"push_repo_url", "control_state", "attribution_skill_key"} <= {
            row[1] for row in conn.execute("PRAGMA table_info(evolution_runs)")
        }
        assert "eval_paused_seconds" in {
            row[1] for row in conn.execute("PRAGMA table_info(evolution_rounds)")
        }
