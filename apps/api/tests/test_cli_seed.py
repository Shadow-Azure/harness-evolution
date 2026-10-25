"""Seed CLI behavior for the M1 shell."""

import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.cli import SeedEnvironmentError, load_seed_manifest, run_seed
from app.config import DatabaseDialect, ServicePhase, Settings


def settings_for(tmp_path: Path, *, phase: ServicePhase = ServicePhase.DEMO) -> Settings:
    """Create a disposable SQLite target with one deterministic administrator."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}",
        phase=phase,
        admin_username="admin",
        admin_password=SecretStr("temporary-password"),
    )


def write_manifest(tmp_path: Path, payload: dict[str, object] | None = None) -> Path:
    """Write the small M1 seed manifest used by real CLI invocations."""
    manifest = tmp_path / "m1-shell.json"
    manifest.write_text(
        json.dumps(
            payload
            or {
                "version": 1,
                "scope": "m1-shell",
                "actions": ["identity-admin"],
            }
        ),
        encoding="utf-8",
    )
    return manifest


async def test_seed_is_idempotent_and_creates_no_domain_rows(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    manifest = write_manifest(tmp_path)

    first = await run_seed(settings, load_seed_manifest(manifest))
    second = await run_seed(settings, load_seed_manifest(manifest))

    assert first.admin_user_id == second.admin_user_id
    with sqlite3.connect(tmp_path / "seed.db") as connection:
        user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        domain_counts = {
            "session_families": connection.execute(
                "SELECT COUNT(*) FROM session_families"
            ).fetchone()[0],
            "bad_cases": connection.execute("SELECT COUNT(*) FROM bad_cases").fetchone()[0],
            "probe_reports": connection.execute("SELECT COUNT(*) FROM probe_reports").fetchone()[0],
            "evolution_targets": connection.execute(
                "SELECT COUNT(*) FROM evolution_targets"
            ).fetchone()[0],
        }
    assert user_count == 1
    assert set(domain_counts.values()) == {0}


def test_seed_manifest_rejects_unknown_fields(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        {
            "version": 1,
            "scope": "m1-shell",
            "actions": ["identity-admin"],
            "fabricateSessions": True,
        },
    )

    with pytest.raises(ValueError, match="fabricateSessions"):
        load_seed_manifest(manifest)


async def test_seed_rejects_live_and_production_targets(tmp_path: Path) -> None:
    manifest = load_seed_manifest(write_manifest(tmp_path))

    with pytest.raises(SeedEnvironmentError, match="live"):
        await run_seed(settings_for(tmp_path, phase=ServicePhase.LIVE), manifest)

    production = settings_for(tmp_path).model_copy(update={"production": True})
    with pytest.raises(SeedEnvironmentError, match="production"):
        await run_seed(production, manifest)


async def test_seed_without_admin_credentials_reports_noop(tmp_path: Path) -> None:
    """A manifest action without configured identity inputs does not claim a write."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'noop.db'}",
        phase=ServicePhase.DEMO,
    )

    result = await run_seed(settings, load_seed_manifest(write_manifest(tmp_path)))

    assert result.admin_user_id is None
    assert result.status == "noop"
