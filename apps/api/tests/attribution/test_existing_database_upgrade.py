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


@pytest.mark.parametrize("revision", ["0022", "0023", "0028"])
def test_existing_database_reaches_head(tmp_path: Path, revision: str) -> None:
    """Main 0022/0023 and the interrupted upgrade at 0028 all lack report V2."""
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
            "SELECT probe_analysis, analyzed_at, attribution_skill_name FROM probe_reports "
            "WHERE probe_id = 'existing'"
        ).fetchone() == ("prior analysis", "2026-11-01", None)
