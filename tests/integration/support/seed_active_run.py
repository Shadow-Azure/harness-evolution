"""Seed one active evolution run for the real proxy integration test."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import insert

from app.config import Settings
from app.db.factory import create_database
from app.db.models.evolution import evolution_runs


async def main() -> None:
    """Insert the requested active run into the configured integration database."""
    run_id = sys.argv[1]
    database = create_database(Settings())
    await database.start()
    try:
        async with database.transaction() as session:
            await session.execute(
                insert(evolution_runs).values(
                    id=run_id,
                    title=f"{run_id} integration",
                    mode="full",
                    engine_key="full",
                    eval_config={},
                    target_config_id=None,
                    target_type="skill",
                    target_name="deep-research",
                    target_version="v2.0.0",
                    repo_url="https://example.invalid/skills.git",
                    sub_dir="skills/deep-research",
                    repo_path=None,
                    base_ref="v2.0.0",
                    base_commit=None,
                    branch_name=f"evo/{run_id}",
                    workspace_path=None,
                    remote_name="origin",
                    push_status="pending",
                    pushed_at=None,
                    push_error=None,
                    window_from=None,
                    window_to=None,
                    models=[],
                    status="running",
                    blocked_stage=None,
                    retry_attempts=0,
                    next_retry_at=None,
                    eval_status="pending",
                    error_stage=None,
                    error_message=None,
                    error_at=None,
                    progress_unit=0,
                    stats={},
                    created_by=None,
                    created_at=datetime.now(UTC),
                    finished_at=None,
                ),
            )
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
