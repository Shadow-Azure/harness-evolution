#!/usr/bin/env python3
"""Seed one anchored and one trigger-line-less case for m12-10 E2E."""

from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.crud.fixtures import backfill_legacy_associations
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import agent_events, bad_cases
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.utils.time import now_shanghai

ROOT_SESSION = "10000000-0000-4000-8000-000000000001"
TRIGGER_LINE = 2
SKILL_NAME = "m12-10-anchor-skill"


def _case(
    case_id: str,
    *,
    object_name: str,
    bad_case_agent_id: str | None,
    trigger_line: int | None,
    now,
) -> dict[str, object]:
    """Build one report at the database column boundary."""
    return {
        "bad_case_id": case_id,
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "bad_case_session_id": ROOT_SESSION,
        "bad_case_type": "self",
        "object_name": object_name,
        "object_type": "skill",
        "object_version": "v1",
        "bad_case_agent_id": bad_case_agent_id,
        "trigger_line": trigger_line,
        "title": f"m12-10 {case_id}",
        "bad_case_description": "m12-10 E2E trigger-point fixture.",
        "meta_data": None,
        "source": "m12-10-e2e",
        "created_at": now,
        "updated_at": now,
    }


async def _seed(data_dir: Path) -> None:
    settings = Settings(
        data_dir=data_dir,
        db_dialect=DatabaseDialect.SQLITE,
        jwt_secret=SecretStr("m12-10-e2e-seed-signing-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        await ensure_fixture_external_tables(database)
        now = now_shanghai() - timedelta(minutes=5)
        async with database.transaction() as session:
            event_index = (
                await session.execute(
                    select(agent_events.c.event_index)
                    .where(agent_events.c.agent_id == ROOT_SESSION)
                    .order_by(agent_events.c.event_index.desc())
                    .limit(1),
                )
            ).scalar_one_or_none()
            await session.execute(
                agent_events.insert().values(
                    agent_id=ROOT_SESSION,
                    event_index=(event_index or 0) + 1,
                    line_no=TRIGGER_LINE,
                    message_offset=1,
                    kind="skill",
                    name=SKILL_NAME,
                    description="m12-10 anchored trigger",
                    tool_use_id="m12-10-tool",
                ),
            )
            await session.execute(
                bad_cases.insert(),
                [
                    _case(
                        "m12-10-anchored",
                        object_name=SKILL_NAME,
                        bad_case_agent_id=ROOT_SESSION,
                        trigger_line=TRIGGER_LINE,
                        now=now,
                    ),
                    _case(
                        "m12-10-l0",
                        object_name="deep-research",
                        bad_case_agent_id=None,
                        trigger_line=0,
                        now=now - timedelta(minutes=1),
                    ),
                    _case(
                        "m12-10-l58",
                        object_name="Explore",
                        bad_case_agent_id=None,
                        trigger_line=58,
                        now=now - timedelta(minutes=2),
                    ),
                    _case(
                        "m12-10-l91",
                        object_name="workflow",
                        bad_case_agent_id=None,
                        trigger_line=91,
                        now=now - timedelta(minutes=3),
                    ),
                    _case(
                        "m12-10-null",
                        object_name="m12-10-missing-skill",
                        bad_case_agent_id=None,
                        trigger_line=None,
                        now=now - timedelta(minutes=4),
                    ),
                ],
            )
        await backfill_legacy_associations(database)
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_seed(args.data_dir))
    print("prepared m12-10 trigger-point fixtures", flush=True)


if __name__ == "__main__":
    main()
