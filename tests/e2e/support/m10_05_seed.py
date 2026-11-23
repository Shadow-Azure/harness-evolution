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
from app.db.models.domain import agent_events, evolution_targets, probe_reports, session_families
from app.utils.definition import digest_revision
from app.utils.time import SHANGHAI

TARGET_ID = "30000000-0000-4000-8000-000000000001"
SKILL_AGENT_ID = "10000000-0000-4000-8000-000000000003"
SESSION_ID = "10000000-0000-4000-8000-000000000003"
OBJECT_VERSION = "synthetic-1"
OBJECT_REVISION = "tag:synthetic-1"
SKILL_TRIGGERED_AT = datetime(2026, 10, 22, 11, 0, tzinfo=SHANGHAI)
# The first prompt is long, as in production SWE-bench sessions; short_title keeps
# the production derivation (first 120 characters) so the table must clamp it.
LONG_TITLE = (
    "You are an autonomous software engineer working in the repository at /testbed. "
    "Solve the issue by editing the repository and running the test suite until it passes."
)


async def _seed(data_dir: Path, repo_url: str | None, *, long_title: bool = False) -> None:
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
                .values(
                    default_ref=OBJECT_VERSION,
                    **({"repo_url": repo_url} if repo_url else {}),
                ),
            )
            await session.execute(
                update(probe_reports)
                .where(probe_reports.c.probe_id == "probe-synthetic-0002")
                .values(object_version=digest_revision("# synthetic-review"), attribution_skill_name="attribute-badcases"),
            )
            if long_title:
                await session.execute(
                    update(session_families)
                    .where(session_families.c.id == SESSION_ID)
                    .values(title=LONG_TITLE, short_title=LONG_TITLE[:120]),
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
    parser.add_argument("--repo-url", default=None)
    parser.add_argument(
        "--long-title",
        action="store_true",
        help="replace the shared session title with a long prompt for the step 2 clamp",
    )
    args = parser.parse_args()
    asyncio.run(_seed(args.data_dir, args.repo_url, long_title=args.long_title))
    print(f"prepared m10-05 preview data in {args.data_dir}", flush=True)


if __name__ == "__main__":
    main()
