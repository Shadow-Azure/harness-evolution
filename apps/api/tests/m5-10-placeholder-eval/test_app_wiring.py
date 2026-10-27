"""Composition-root checks for placeholder evaluation."""

from pathlib import Path

from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.main import create_app


def test_create_app_registers_apply_finalize_and_poller(tmp_path: Path) -> None:
    """The production composition exposes every automatic evaluation follow-up."""
    app = create_app(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m5-10-composition-secret"),
            eval_scan_seconds=1,
            eval_poll_seconds=2,
            eval_timeout_seconds=3,
        ),
    )

    assert {
        "evolution_prepare",
        "evolution_advance",
        "evolution_apply",
        "evolution_finalize",
    }.issubset(app.state.jobs._handlers)
    assert app.state.evolution_eval_poller is not None
    assert "/api/evolution/runs/{run_id}/advance" not in app.openapi()["paths"]
    assert "/api/evolution/runs/{run_id}/push" not in app.openapi()["paths"]
