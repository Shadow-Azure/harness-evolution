#!/usr/bin/env python3
"""Seed the m11-04 target-overview smoke data on top of the demo corpus.

The demo corpus contains one configured target with a single attributed row.
The target overview needs the other two attribution states, a second page of
targets and an observable version split, so this helper adds deterministic
bad cases, attribution links, and extra target configurations. It is intended
for one throwaway SQLite data directory produced by ``pnpm fixtures:seed``.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import delete, select

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    bad_case_analysis,
    bad_cases,
    evolution_targets,
    probe_reports,
)
from app.utils.time import SHANGHAI

BASE_CASE_ID = "badcase-synthetic-0003"
NON_TARGET_CASE_ID = "badcase-m11-04-nontarget"
UNANALYZED_CASE_ID = "badcase-m11-04-unanalyzed"
NON_TARGET_PROBE_ID = "probe-m11-04-nontarget"
EXTRA_TARGET_IDS = [
    "40000000-0000-4000-8000-000000000001",
    "40000000-0000-4000-8000-000000000002",
    "40000000-0000-4000-8000-000000000003",
    "40000000-0000-4000-8000-000000000004",
    "40000000-0000-4000-8000-000000000005",
]

NON_TARGET_AT = datetime(2026, 10, 24, 9, 10, tzinfo=SHANGHAI)
UNANALYZED_AT = datetime(2026, 10, 24, 9, 20, tzinfo=SHANGHAI)


def _case_row(
    base: dict[str, object],
    *,
    case_id: str,
    title: str,
    created_at: datetime,
) -> dict[str, object]:
    """Clone one fixture case into a deterministic in-window case."""
    row = dict(base)
    row.update(
        {
            "bad_case_id": case_id,
            "title": title,
            "bad_case_description": f"m11-04 target overview smoke case {case_id}",
            "created_at": created_at,
            "updated_at": created_at,
        },
    )
    return row


async def _seed(data_dir: Path) -> None:
    settings = Settings(
        data_dir=data_dir,
        db_dialect=DatabaseDialect.SQLITE,
        jwt_secret=SecretStr("m11-04-target-overview-seed-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        await ensure_fixture_external_tables(database)
        async with database.transaction() as session:
            base = (
                await session.execute(
                    select(bad_cases).where(
                        bad_cases.c.bad_case_id == BASE_CASE_ID,
                    ),
                )
            ).mappings().one()
            base_row = dict(base)
            workspace_id = str(base_row["workspace_id"])
            session_id = str(base_row["bad_case_session_id"])

            for case_id, title, created_at in (
                (NON_TARGET_CASE_ID, "非该对象问题的潜在 bad case", NON_TARGET_AT),
                (UNANALYZED_CASE_ID, "尚未分析的潜在 bad case", UNANALYZED_AT),
            ):
                exists = (
                    await session.execute(
                        select(bad_cases.c.bad_case_id).where(
                            bad_cases.c.bad_case_id == case_id,
                        ),
                    )
                ).first()
                row = _case_row(
                    base_row,
                    case_id=case_id,
                    title=title,
                    created_at=created_at,
                )
                row["workspace_id"] = workspace_id
                row["bad_case_session_id"] = session_id
                row["bad_case_type"] = "self"
                row["object_name"] = "synthetic-review"
                row["object_type"] = "skill"
                row["object_version"] = "synthetic-1"
                row["source"] = "Explore"
                if exists is None:
                    await session.execute(bad_cases.insert().values(**row))

            probe = {
                "probe_id": NON_TARGET_PROBE_ID,
                "workspace_id": workspace_id,
                "session_id": session_id,
                "probe_type": "skill",
                "probe_object": "synthetic-review",
                "object_version": "synthetic-1",
                "attribute_type": "error",
                "conclusion": "non_target",
                "confidence": 0.71,
                "probe_description": "触发点在 bad case 之后，归为非该对象问题。",
                "probe_analysis": "1. 对象触发点晚于异常分支。\n2. 输入来源与该对象无交集。",
                "policy_version": "v2",
                "attribution_engine": "m11-04-smoke",
                "reused_count": 0,
                "created_at": NON_TARGET_AT,
                "updated_at": NON_TARGET_AT,
            }
            exists = (
                await session.execute(
                    select(probe_reports.c.probe_id).where(
                        probe_reports.c.probe_id == NON_TARGET_PROBE_ID,
                    ),
                )
            ).first()
            if exists is None:
                await session.execute(probe_reports.insert().values(**probe))

            await session.execute(
                delete(bad_case_analysis).where(
                    bad_case_analysis.c.bad_case_id == NON_TARGET_CASE_ID,
                ),
            )
            await session.execute(
                bad_case_analysis.insert().values(
                    bad_case_id=NON_TARGET_CASE_ID,
                    analysis_status="analyzed_nonissue",
                    probe_id=NON_TARGET_PROBE_ID,
                    analysis_result={"summary": "非该对象问题"},
                    updated_at=NON_TARGET_AT,
                ),
            )
            await session.execute(
                delete(bad_case_analysis).where(
                    bad_case_analysis.c.bad_case_id == UNANALYZED_CASE_ID,
                ),
            )

            for index, target_id in enumerate(EXTRA_TARGET_IDS, start=1):
                exists = (
                    await session.execute(
                        select(evolution_targets.c.id).where(
                            evolution_targets.c.id == target_id,
                        ),
                    )
                ).first()
                if exists is None:
                    await session.execute(
                        evolution_targets.insert().values(
                            id=target_id,
                            workspace_id=workspace_id,
                            object_type="skill",
                            object_name=f"m11-04-extra-{index}",
                            repo_url="https://example.invalid/m11-04.git",
                            sub_dir=f"skills/extra-{index}",
                            default_ref="main",
                            validation_project_id=f"val-m11-04-{index}",
                            test_project_id=f"test-m11-04-{index}",
                            enabled=True,
                            created_at=NON_TARGET_AT,
                            updated_at=NON_TARGET_AT,
                        ),
                    )
        print(
            f"seeded m11-04 target overview data in {data_dir} for {workspace_id}",
            flush=True,
        )
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_seed(args.data_dir))


if __name__ == "__main__":
    main()
