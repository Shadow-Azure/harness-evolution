#!/usr/bin/env python3
"""Seed one bad_cases root for the bad-case trajectory sync smoke run."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_cases
from app.utils.time import now_shanghai


async def _seed(data_dir: Path, root_session_id: str) -> None:
    settings = Settings(data_dir=data_dir, db_dialect=DatabaseDialect.SQLITE)
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        await ensure_fixture_external_tables(database)
        now = now_shanghai()
        async with database.transaction() as session:
            exists = (
                await session.execute(
                    bad_cases.select().where(
                        bad_cases.c.bad_case_id == "smoke-bad-case",
                    ),
                )
            ).first()
            if exists is None:
                await session.execute(
                    bad_cases.insert().values(
                        bad_case_id="smoke-bad-case",
                        bad_case_session_id=root_session_id,
                        bad_case_type="error",
                        object_name="deep-research",
                        object_type="skill",
                        object_version="v1",
                        bad_case_agent_id=None,
                        title="smoke bad case",
                        bad_case_description="smoke bad case description",
                        meta_data=None,
                        source="smoke",
                        created_at=now,
                        updated_at=now,
                    ),
                )
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--root",
        default="11111111-1111-4111-8111-111111111111",
    )
    args = parser.parse_args()
    asyncio.run(_seed(args.data_dir, args.root))
    print(f"seeded bad_cases root {args.root}", flush=True)


if __name__ == "__main__":
    main()
