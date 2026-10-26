"""Insert deterministic evolution runs for the M5-04 browser smoke."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, insert, select

from app.config import Settings
from app.db.factory import create_database
from app.db.models.evolution import (
    evolution_finals,
    evolution_rounds,
    evolution_runs,
    probe_clusters,
)
from app.db.models.users import users

CREATED_BASE = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def _run(
    run_id: str,
    status: str,
    *,
    minutes_ago: int,
    created_by: str,
    clusters: int,
    progress_unit: int,
    article_type: str = "skill",
    error: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Build one complete run row with deterministic snapshots."""
    created_at = CREATED_BASE - timedelta(minutes=minutes_ago)
    return {
        "id": run_id,
        "title": f"{run_id} 自进化",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {},
        "target_config_id": None,
        "target_type": article_type,
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "repo_path": None,
        "base_ref": "v2.0.0",
        "base_commit": None,
        "branch_name": f"evo/{run_id}",
        "workspace_path": None,
        "remote_name": "origin",
        "push_status": "succeeded",
        "pushed_at": created_at,
        "push_error": None,
        "window_from": date(2026, 8, 20),
        "window_to": date(2026, 9, 10),
        "models": ["glm-5.3", "gpt-5"],
        "status": status,
        "blocked_stage": "eval" if status == "blocked" else None,
        "retry_attempts": 0,
        "next_retry_at": None,
        "eval_status": "pending",
        "error_stage": error[0] if error else None,
        "error_message": error[1] if error else None,
        "error_at": created_at if error else None,
        "progress_unit": progress_unit,
        "stats": {
            "sessions": 128,
            "probes": 46,
            "usedProbes": 999,
            "clusters": 999,
            "byAttributeType": {
                "model": 12,
                "prompt": 8,
                "error": 8,
                "nonIssue": 18,
            },
        },
        "created_by": created_by,
        "created_at": created_at,
        "finished_at": created_at + timedelta(minutes=5)
        if status in {"completed", "failed", "interrupted"}
        else None,
    }


async def main() -> None:
    """Replace the run tables with eight deterministic status cards."""
    settings = Settings()
    database = create_database(settings)
    await database.start()
    try:
        async with database.transaction() as session:
            admin_id = (
                await session.execute(
                    select(users.c.id).where(users.c.username == "admin"),
                )
            ).scalar_one()
            await session.execute(delete(evolution_runs))
            rows = [
                _run(
                    "run-running",
                    "running",
                    minutes_ago=0,
                    created_by=admin_id,
                    clusters=2,
                    progress_unit=4,
                ),
                _run(
                    "run-blocked",
                    "blocked",
                    minutes_ago=60,
                    created_by=admin_id,
                    clusters=1,
                    progress_unit=4,
                    error=("eval", "评测队列暂停"),
                ),
                _run(
                    "run-preparing",
                    "preparing",
                    minutes_ago=120,
                    created_by=admin_id,
                    clusters=0,
                    progress_unit=0,
                ),
                _run(
                    "run-completed-effective",
                    "completed",
                    minutes_ago=180,
                    created_by=admin_id,
                    clusters=2,
                    progress_unit=7,
                ),
                _run(
                    "run-failed",
                    "failed",
                    minutes_ago=240,
                    created_by=admin_id,
                    clusters=1,
                    progress_unit=4,
                    error=("eval", "评测执行失败：sandbox timeout"),
                ),
                _run(
                    "run-interrupted",
                    "interrupted",
                    minutes_ago=300,
                    created_by=admin_id,
                    clusters=1,
                    progress_unit=4,
                    error=("push", "推送连接中断"),
                ),
                _run(
                    "run-completed-no-benefit",
                    "completed",
                    minutes_ago=360,
                    created_by=admin_id,
                    clusters=2,
                    progress_unit=7,
                ),
                _run(
                    "run-completed-unknown",
                    "completed",
                    minutes_ago=420,
                    created_by=admin_id,
                    clusters=2,
                    progress_unit=7,
                ),
            ]
            await session.execute(insert(evolution_runs), rows)

            cluster_rows: list[dict[str, Any]] = []
            round_rows: list[dict[str, Any]] = []
            for run in rows:
                count = {
                    "run-running": 2,
                    "run-blocked": 1,
                    "run-preparing": 0,
                    "run-completed-effective": 2,
                    "run-failed": 1,
                    "run-interrupted": 1,
                    "run-completed-no-benefit": 2,
                    "run-completed-unknown": 2,
                }[str(run["id"])]
                for seq in range(1, count + 1):
                    cluster_id = f"{run['id']}-cluster-{seq}"
                    cluster_rows.append(
                        {
                            "probe_cluster_id": cluster_id,
                            "run_id": run["id"],
                            "seq": seq,
                            "probe_cluster_description": f"cluster {seq}",
                            "probe_cluster_type": "error",
                            "confidence": 0.82,
                            "impact": 9,
                            "severity": 7.4,
                            "rank": seq,
                            "created_at": CREATED_BASE,
                        },
                    )
                    if run["id"] == "run-completed-effective" and seq == 1:
                        round_rows.append(
                            {
                                "id": "round-completed-effective-1",
                                "run_id": run["id"],
                                "probe_cluster_id": cluster_id,
                                "seq": 1,
                                "status": "accepted",
                                "accepted": True,
                            },
                        )
            await session.execute(insert(probe_clusters), cluster_rows)
            if round_rows:
                await session.execute(insert(evolution_rounds), round_rows)
            await session.execute(
                insert(evolution_finals),
                [
                    {
                        "run_id": "run-completed-effective",
                        "best_version": "v2.0.1-best",
                        "verdict": True,
                        "best_score": 88.9,
                        "init_score": 84.3,
                        "metrics": [],
                    },
                    {
                        "run_id": "run-completed-no-benefit",
                        "best_version": "v2.0.0",
                        "verdict": False,
                        "best_score": 80.1,
                        "init_score": 80.1,
                        "metrics": [],
                    },
                ],
            )
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
