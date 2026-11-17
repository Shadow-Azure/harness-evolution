#!/usr/bin/env python3
"""Seed deterministic preview/launch data for the m10-05 wizard smoke run."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import update

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import agent_events, evolution_targets
from app.utils.time import SHANGHAI

TARGET_ID = "30000000-0000-4000-8000-000000000001"
SKILL_AGENT_ID = "10000000-0000-4000-8000-000000000003"
OBJECT_VERSION = "synthetic-1"
OBJECT_REVISION = "tag:synthetic-1"
SKILL_TRIGGERED_AT = datetime(2026, 10, 22, 11, 0, tzinfo=SHANGHAI)


async def _seed(data_dir: Path) -> None:
    settings = Settings(
        data_dir=data_dir,
        db_dialect=DatabaseDialect.SQLITE,
        jwt_secret=SecretStr("m10-05-launch-seed-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        await ensure_fixture_external_tables(database)
        async with database.transaction() as session:
            await session.execute(
                update(evolution_targets)
                .where(evolution_targets.c.id == TARGET_ID)
                .values(default_ref=OBJECT_VERSION),
            )
            await session.execute(
                update(agent_events)
                .where(
                    agent_events.c.agent_id == SKILL_AGENT_ID,
                    agent_events.c.event_index == 0,
                )
                .values(
                    object_version=OBJECT_VERSION,
                    object_revision=OBJECT_REVISION,
                    triggered_at=SKILL_TRIGGERED_AT,
                ),
            )
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_seed(args.data_dir))
    print(f"prepared m10-05 preview data in {args.data_dir}", flush=True)


if __name__ == "__main__":
    main()
