#!/usr/bin/env python3
"""Seed m12-07 trace states: one ready case and four unready roots."""

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
from app.db.models.domain import bad_case_root_sync, bad_cases, session_families
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.utils.time import now_shanghai

PENDING_ROOT = "30000000-0000-4000-8000-000000000101"
SYNCING_ROOT = "30000000-0000-4000-8000-000000000102"
FAILED_ROOT = "30000000-0000-4000-8000-000000000103"
UNAVAILABLE_ROOT = "30000000-0000-4000-8000-000000000104"


def _case(case_id: str, session_id: str, now):
    return {
        "bad_case_id": case_id,
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "bad_case_session_id": session_id,
        "bad_case_type": "self",
        "object_name": "claude-code",
        "object_type": "agent",
        "object_version": "v1",
        "bad_case_agent_id": None,
        "title": f"[SWE-bench] {case_id}",
        "bad_case_description": "m12-07 E2E trace state fixture.",
        "meta_data": None,
        "source": "m12-07-e2e",
        "created_at": now,
        "updated_at": now,
    }


def _state(root: str, status: str, error: str | None, now, **extra):
    values = {
        "root_session_id": root,
        "status": status,
        "source_kind": "global",
        "source_snapshot": {"kind": "global"},
        "attempts": 1,
        "last_error": error,
        "agent_count": 0,
        "started_at": now,
        "synced_at": now if status == "synced" else None,
        "next_retry_at": None,
        "lease_owner": None,
        "lease_expires_at": None,
        "updated_at": now,
    }
    values.update(extra)
    return values


async def _seed(data_dir: Path) -> None:
    settings = Settings(
        data_dir=data_dir,
        db_dialect=DatabaseDialect.SQLITE,
        jwt_secret=SecretStr("m12-07-e2e-seed-signing-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        await ensure_fixture_external_tables(database)
        now = now_shanghai()
        async with database.transaction() as session:
            ready_session = (
                await session.execute(
                    select(session_families.c.id)
                    .order_by(session_families.c.started_at)
                    .limit(1),
                )
            ).scalar_one()
            cases = [
                _case("m12-07-ready", ready_session, now),
                _case("m12-07-pending", PENDING_ROOT, now),
                _case("m12-07-syncing", SYNCING_ROOT, now),
                _case("m12-07-failed", FAILED_ROOT, now),
                _case("m12-07-unavailable", UNAVAILABLE_ROOT, now),
            ]
            await session.execute(bad_cases.insert(), cases)
            await session.execute(
                bad_case_root_sync.insert(),
                [
                    _state(ready_session, "synced", None, now),
                    _state(SYNCING_ROOT, "syncing", None, now),
                    _state(
                        FAILED_ROOT,
                        "failed",
                        "SESSION_QUERY_TIMEOUT",
                        now,
                        next_retry_at=now - timedelta(minutes=1),
                    ),
                    _state(
                        UNAVAILABLE_ROOT,
                        "failed",
                        "SESSION_QUERY_UNAVAILABLE",
                        now,
                        next_retry_at=now - timedelta(minutes=1),
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
    print("prepared m12-07 trace states", flush=True)


if __name__ == "__main__":
    main()
