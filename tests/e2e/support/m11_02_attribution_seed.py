#!/usr/bin/env python3
"""Seed several object-attributions for one bad case in the m11-02 smoke run.

The demo corpus links each bad case to a single probe report, which cannot
exercise the V2 folded attribution list. This helper appends two attributed
rows and one non-target row to a deterministic case so pagination, deep links
and the two conclusion banners have real data.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import select

from app.config import DatabaseDialect, Settings
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_case_analysis, bad_cases, probe_reports
from app.utils.time import SHANGHAI

DEFAULT_CASE_ID = "badcase-synthetic-0001"
DEFAULT_SESSION_ID = "10000000-0000-4000-8000-000000000001"


def _row(
    probe_id: str,
    *,
    session_id: str,
    probe_type: str,
    probe_object: str,
    object_version: str | None,
    attribute_type: str | None,
    conclusion: str,
    confidence: float,
    description: str,
    analysis: str,
    updated_at: datetime,
) -> dict[str, object]:
    """Build one complete probe row shared by the seed and the analysis link."""
    return {
        "probe_id": probe_id,
        "session_id": session_id,
        "probe_type": probe_type,
        "probe_object": probe_object,
        "object_version": object_version,
        "attribute_type": attribute_type,
        "conclusion": conclusion,
        "confidence": confidence,
        "probe_description": description,
        "probe_analysis": analysis,
        "policy_version": "v2",
        "attribution_engine": "m11-02-smoke",
        "reused_count": 0,
        "created_at": updated_at,
        "updated_at": updated_at,
    }


async def _seed(data_dir: Path, case_id: str, session_id: str) -> int:
    settings = Settings(
        data_dir=data_dir,
        db_dialect=DatabaseDialect.SQLITE,
        jwt_secret=SecretStr("m11-02-attribution-seed-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        await ensure_fixture_external_tables(database)
        async with database.transaction() as session:
            workspace_id = (
                await session.execute(
                    select(bad_cases.c.workspace_id).where(
                        bad_cases.c.bad_case_id == case_id,
                    ),
                )
            ).scalar_one()
            rows = [
                _row(
                    "probe-m11-02-0001",
                    session_id=session_id,
                    probe_type="skill",
                    probe_object="checklist-skill",
                    object_version="2026.11.1",
                    attribute_type="flow",
                    conclusion="attributed",
                    confidence=0.86,
                    description=(
                        "检查清单技能把未完成项误判为通过；该 bad case 的结论"
                        "可追溯到 checklist-skill 的输出。"
                    ),
                    analysis=(
                        "1. 在会话轨迹中定位 checklist-skill 的调用点。\n"
                        "2. 对照检查项清单，确认完成状态读取错误。\n"
                        "3. 该输出直接进入 bad case 的汇总分支，判定可归因。"
                    ),
                    updated_at=datetime(2026, 10, 20, 9, 5, tzinfo=SHANGHAI),
                ),
                _row(
                    "probe-m11-02-0002",
                    session_id=session_id,
                    probe_type="agent",
                    probe_object="review-agent",
                    object_version="2026.11.2",
                    attribute_type=None,
                    conclusion="non_target",
                    confidence=0.74,
                    description=(
                        "review-agent 的触发点在 bad case 之后，异常输入不由该"
                        "对象产生，因此记为非该对象问题。"
                    ),
                    analysis=(
                        "1. review-agent 在汇总阶段之后才启动。\n"
                        "2. 输入来源与异常分支没有交集。\n"
                        "3. 结论为非该对象问题，不影响其他对象的潜在关系。"
                    ),
                    updated_at=datetime(2026, 10, 20, 9, 6, tzinfo=SHANGHAI),
                ),
                _row(
                    "probe-m11-02-0003",
                    session_id=session_id,
                    probe_type="knowledge",
                    probe_object="project-knowledge",
                    object_version=None,
                    attribute_type="context",
                    conclusion="attributed",
                    confidence=0.68,
                    description=(
                        "知识库条目缺少目标文件约束，归因到 project-knowledge"
                        " 的未固定版本。"
                    ),
                    analysis=(
                        "1. 检索命中的知识条目没有固定版本。\n"
                        "2. 检索结果缺少输出文件约束，导致目标文件遗漏。\n"
                        "3. 结论只作用于该对象版本。"
                    ),
                    updated_at=datetime(2026, 10, 20, 9, 7, tzinfo=SHANGHAI),
                ),
            ]
            for row in rows:
                row["workspace_id"] = workspace_id
                exists = (
                    await session.execute(
                        select(probe_reports.c.probe_id).where(
                            probe_reports.c.probe_id == row["probe_id"],
                        ),
                    )
                ).first()
                if exists is None:
                    await session.execute(probe_reports.insert().values(**row))
                await session.execute(
                    bad_case_analysis.delete().where(
                        bad_case_analysis.c.bad_case_id == case_id,
                        bad_case_analysis.c.probe_id == row["probe_id"],
                    ),
                )
                await session.execute(
                    bad_case_analysis.insert().values(
                        bad_case_id=case_id,
                        analysis_status="analyzed_issue",
                        probe_id=row["probe_id"],
                        analysis_result={"summary": row["probe_object"]},
                        updated_at=row["updated_at"],
                    ),
                )
        return len(rows)
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--case-id", default=DEFAULT_CASE_ID)
    parser.add_argument("--session-id", default=DEFAULT_SESSION_ID)
    args = parser.parse_args()
    inserted = asyncio.run(_seed(args.data_dir, args.case_id, args.session_id))
    print(
        f"seeded {inserted} attribute rows for {args.case_id} in {args.data_dir}",
        flush=True,
    )


if __name__ == "__main__":
    main()
