"""Create, complete, or delete evolution runs for M5 browser smoke fixtures."""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import delete, insert, update

from app.config import Settings
from app.db.factory import create_database
from app.db.models.evolution import evolution_runs
from app.utils.ids import new_id
from app.utils.time import now_shanghai


async def main() -> None:
    """Apply one test-only run lifecycle operation to the configured database."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "complete", "delete"))
    parser.add_argument("value")
    args = parser.parse_args()
    database = create_database(Settings())
    await database.start()
    try:
        async with database.transaction() as session:
            if args.action == "create":
                run_id = new_id()
                now = now_shanghai()
                await session.execute(
                    insert(evolution_runs).values(
                        id=run_id,
                        title="M5 target in-use smoke",
                        mode="full",
                        engine_key="full",
                        eval_config={},
                        target_config_id=args.value,
                        target_type="skill",
                        target_name="m5-e2e-target",
                        target_version="v2.0.0",
                        repo_url="https://git.example.com/agent-skills.git",
                        sub_dir="skills/m5-e2e-target",
                        remote_name="origin",
                        push_status="pending",
                        models=[],
                        status="running",
                        retry_attempts=0,
                        eval_status="pending",
                        progress_unit=0,
                        stats={},
                        created_at=now,
                    ),
                )
                print(run_id)
            elif args.action == "complete":
                await session.execute(
                    update(evolution_runs)
                    .where(evolution_runs.c.id == args.value)
                    .values(status="completed", finished_at=now_shanghai()),
                )
            else:
                await session.execute(
                    delete(evolution_runs).where(evolution_runs.c.id == args.value),
                )
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
