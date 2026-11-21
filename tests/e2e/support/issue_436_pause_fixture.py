"""Seed a synthetic run waiting on an existing external evaluation."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import delete, update

from app.config import Settings
from app.db.factory import create_database
from app.db.models.evolution import evolution_finals, evolution_rounds, evolution_runs
from app.utils.time import now_shanghai
from m10_06_run_detail_fixture import main as seed_detail


async def main() -> None:
    """Reuse reached-step fixtures; leave an evaluation pending for browser controls."""
    await seed_detail()
    database = create_database(Settings())
    await database.start()
    now = now_shanghai()
    try:
        async with database.transaction() as session:
            await session.execute(
                delete(evolution_finals).where(
                    evolution_finals.c.run_id == "run-v2-completed"
                )
            )
            await session.execute(
                update(evolution_runs)
                .where(evolution_runs.c.id == "run-v2-completed")
                .values(
                    title="deep-research v2.0.0 自进化",
                    status="running",
                    progress_unit=5,
                    control_state="running",
                    eval_status="evaluating",
                    finished_at=None,
                )
            )
            await session.execute(
                update(evolution_rounds)
                .where(evolution_rounds.c.id == "v2-round-1")
                .values(
                    status="evaluating",
                    accepted=False,
                    commit_hash=None,
                    eval_status="evaluating",
                    eval_external_id="synthetic-existing-eval-436",
                    eval_started_at=now,
                    eval_finished_at=None,
                    eval_next_poll_at=now + timedelta(days=1),
                )
            )
            await session.execute(
                update(evolution_rounds)
                .where(evolution_rounds.c.id == "v2-round-2")
                .values(
                    status="pending",
                    accepted=False,
                    eval_status="pending",
                    commit_hash=None,
                )
            )
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
