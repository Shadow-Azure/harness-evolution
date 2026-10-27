"""Insert deterministic evolution runs for the M5-04 browser smoke."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, insert, select

from app.config import Settings
from app.db.factory import create_database
from app.db.models.domain import (
    bad_case_analysis,
    bad_cases,
    probe_reports,
    session_families,
    source_records,
)
from app.db.models.evolution import (
    evolution_finals,
    evolution_rounds,
    evolution_runs,
    probe_cluster_probes,
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
    eval_status = {
        "running": "evaluating",
        "blocked": "failed",
        "completed": "completed",
        "failed": "failed",
    }.get(status, "pending")
    push_status = "succeeded" if clusters else "pending"
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
        "push_status": push_status,
        "pushed_at": created_at if clusters else None,
        "push_error": None,
        "window_from": date(2026, 8, 20),
        "window_to": date(2026, 9, 10),
        "models": ["glm-5.3", "gpt-5"],
        "status": status,
        "blocked_stage": "eval" if status == "blocked" else None,
        "retry_attempts": 0,
        "next_retry_at": None,
        "eval_status": eval_status,
        "error_stage": error[0] if error else None,
        "error_message": error[1] if error else None,
        "error_at": created_at if error else None,
        "progress_unit": progress_unit,
        "stats": {
            "sessions": 128,
            "probes": 46,
            "usedProbes": clusters,
            "clusters": clusters,
            "byAttributeType": {
                "model": 0,
                "prompt": 0,
                "error": clusters,
                "nonIssue": 46 - clusters,
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
            fixture_ids = [
                f"{run_id}-{seq}"
                for run_id in (
                    "run-running",
                    "run-blocked",
                    "run-completed-effective",
                    "run-failed",
                    "run-interrupted",
                    "run-completed-no-benefit",
                    "run-completed-unknown",
                )
                for seq in (1, 2)
            ]
            session_ids = [f"session-{suffix}" for suffix in fixture_ids]
            probe_ids = [f"probe-{suffix}" for suffix in fixture_ids]
            case_ids = [f"case-{suffix}" for suffix in fixture_ids]
            await session.execute(
                delete(bad_case_analysis).where(
                    bad_case_analysis.c.bad_case_id.in_(case_ids),
                ),
            )
            await session.execute(
                delete(bad_cases).where(bad_cases.c.bad_case_id.in_(case_ids)),
            )
            await session.execute(
                delete(probe_reports).where(probe_reports.c.probe_id.in_(probe_ids)),
            )
            await session.execute(
                delete(session_families).where(session_families.c.id.in_(session_ids)),
            )
            await session.execute(
                delete(source_records).where(
                    source_records.c.root_session_id.in_(session_ids),
                ),
            )
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
            cluster_probe_rows: list[dict[str, Any]] = []
            round_rows: list[dict[str, Any]] = []
            session_rows: list[dict[str, Any]] = []
            source_rows: list[dict[str, Any]] = []
            probe_rows: list[dict[str, Any]] = []
            case_rows: list[dict[str, Any]] = []
            analysis_rows: list[dict[str, Any]] = []
            next_source_id = int(
                (
                    await session.execute(
                        select(func.coalesce(func.max(source_records.c.id), 0)),
                    )
                ).scalar_one(),
            )
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
                    suffix = f"{run['id']}-{seq}"
                    session_id = f"session-{suffix}"
                    probe_id = f"probe-{suffix}"
                    case_id = f"case-{suffix}"
                    next_source_id += 1
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
                    cluster_probe_rows.append(
                        {
                            "probe_cluster_id": cluster_id,
                            "probe_id": probe_id,
                        },
                    )
                    source_rows.append(
                        {
                            "id": next_source_id,
                            "root_session_id": session_id,
                            "agent_id": session_id,
                            "kind": "main",
                            "source_type": "synthetic",
                            "line_count": 1,
                            "received_at": CREATED_BASE,
                        },
                    )
                    session_rows.append(
                        {
                            "id": session_id,
                            "short_title": f"来源运行 {seq}",
                            "title": f"来源运行 {seq}",
                            "search_text": f"来源运行 {seq}",
                            "repo_name": "example/repo",
                            "project_path": "/workspace/example",
                            "model": "glm-5.3",
                            "models": ["glm-5.3"],
                            "started_at": CREATED_BASE,
                            "ended_at": CREATED_BASE,
                            "duration_seconds": 1,
                            "status": "completed",
                            "skill_names": ["deep-research"],
                            "user_turns_count": 1,
                            "messages_count": 1,
                            "tools_count": 0,
                            "errors_count": 1,
                            "agents_count": 1,
                            "tokens_total": 1,
                            "source_type": "synthetic",
                            "main_record_id": next_source_id,
                            "imported_at": CREATED_BASE,
                            "updated_at": CREATED_BASE,
                        },
                    )
                    case_rows.append(
                        {
                            "bad_case_id": case_id,
                            "bad_case_session_id": session_id,
                            "bad_case_type": "discovery",
                            "object_name": "deep-research",
                            "object_type": "skill",
                            "object_version": "v2.0.0",
                            "reason": f"检索索引读取失败（来源 {seq}）",
                            "meta_data": {},
                            "source": "fixtures",
                            "created_at": CREATED_BASE,
                            "updated_at": CREATED_BASE,
                        },
                    )
                    probe_rows.append(
                        {
                            "probe_id": probe_id,
                            "session_id": session_id,
                            "probe_type": "skill",
                            "probe_object": "deep-research",
                            "object_version": "v2.0.0",
                            "attribute_type": "error",
                            "probe_description": f"检索索引读取失败（来源 {seq}）",
                            "probe_analysis": (
                                "**确认问题**\n\n"
                                f"- 第 {seq} 条来源缺少快照校验"
                            ),
                            "created_at": CREATED_BASE,
                            "updated_at": CREATED_BASE,
                        },
                    )
                    analysis_rows.append(
                        {
                            "bad_case_id": case_id,
                            "analysis_status": "analyzed_issue",
                            "probe_id": probe_id,
                            "analysis_result": {"summary": "索引读取缺少校验"},
                            "updated_at": CREATED_BASE,
                        },
                    )
                    if run["id"] == "run-running" and seq == 1:
                        round_rows.append(
                            {
                                "id": "round-running-1",
                                "run_id": run["id"],
                                "probe_cluster_id": cluster_id,
                                "seq": 1,
                                "status": "evaluating",
                                "started_at": CREATED_BASE,
                                "patch": {
                                    "file": "SKILL.md",
                                    "lines": [
                                        "@@ -1 +1 @@",
                                        "- 读取索引",
                                        "+ 读取索引前校验快照字段",
                                    ],
                                },
                                "candidate_ref": (
                                    "evo/run-running/candidate/r1"
                                ),
                                "candidate_commit": (
                                    "ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12"
                                ),
                                "candidate_message": (
                                    "evolve(deep-research): 校验快照字段"
                                ),
                                "push_status": "succeeded",
                                "push_attempts": 1,
                                "pushed_at": CREATED_BASE,
                                "eval_status": "evaluating",
                                "eval_attempts": 1,
                                "eval_current": 84.6,
                                "eval_candidate": None,
                                "accepted": False,
                            },
                        )
                    if run["id"] == "run-blocked" and seq == 1:
                        round_rows.append(
                            {
                                "id": "round-blocked-1",
                                "run_id": run["id"],
                                "probe_cluster_id": cluster_id,
                                "seq": 1,
                                "status": "evaluating",
                                "started_at": CREATED_BASE,
                                "error_message": "评测队列暂停",
                                "patch": {
                                    "file": "SKILL.md",
                                    "lines": ["+ 读取索引前校验快照字段"],
                                },
                                "candidate_ref": (
                                    "evo/run-blocked/candidate/r1"
                                ),
                                "candidate_commit": (
                                    "cd34ab12ef56cd34ab12ef56cd34ab12ef56cd34"
                                ),
                                "candidate_message": (
                                    "evolve(deep-research): 校验快照字段"
                                ),
                                "push_status": "succeeded",
                                "push_attempts": 1,
                                "eval_status": "failed",
                                "eval_attempts": 1,
                                "eval_current": 84.6,
                                "eval_error": "评测队列暂停",
                                "accepted": False,
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
                                "patch": {
                                    "file": "SKILL.md",
                                    "lines": ["+ 读取索引前校验快照字段"],
                                },
                                "candidate_ref": (
                                    "evo/run-completed-effective/candidate/r1"
                                ),
                                "candidate_commit": (
                                    "ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12"
                                ),
                                "candidate_message": (
                                    "evolve(deep-research): 校验快照字段"
                                ),
                                "push_status": "succeeded",
                                "push_attempts": 1,
                                "eval_status": "completed",
                                "eval_attempts": 1,
                                "eval_current": 84.3,
                                "eval_candidate": 88.9,
                                "accepted": True,
                                "commit_hash": (
                                    "ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56"
                                ),
                                "commit_message": (
                                    "evolve(deep-research): 校验快照字段"
                                ),
                            },
                        )
            await session.execute(insert(source_records), source_rows)
            await session.execute(insert(session_families), session_rows)
            await session.execute(insert(bad_cases), case_rows)
            await session.execute(insert(probe_reports), probe_rows)
            await session.execute(insert(bad_case_analysis), analysis_rows)
            await session.execute(insert(probe_clusters), cluster_rows)
            if cluster_probe_rows:
                await session.execute(
                    insert(probe_cluster_probes),
                    cluster_probe_rows,
                )
            if round_rows:
                round_defaults: dict[str, Any] = {
                    "started_at": None,
                    "finished_at": None,
                    "duration_ms": None,
                    "error_message": None,
                    "patch": None,
                    "candidate_ref": None,
                    "candidate_commit": None,
                    "candidate_message": None,
                    "push_status": "pending",
                    "push_attempts": 0,
                    "pushed_at": None,
                    "push_error": None,
                    "eval_external_id": None,
                    "eval_status": "pending",
                    "eval_attempts": 0,
                    "eval_next_poll_at": None,
                    "eval_started_at": None,
                    "eval_finished_at": None,
                    "eval_current": None,
                    "eval_candidate": None,
                    "eval_result": None,
                    "eval_error": None,
                    "accepted": False,
                    "commit_hash": None,
                    "commit_message": None,
                }
                normalized_rounds = [
                    {**round_defaults, **row}
                    for row in round_rows
                ]
                await session.execute(
                    insert(evolution_rounds),
                    normalized_rounds,
                )
            await session.execute(
                insert(evolution_finals),
                [
                    {
                        "run_id": "run-completed-effective",
                        "best_version": "v2.0.1-best",
                        "verdict": True,
                        "best_score": 88.9,
                        "init_score": 84.3,
                        "metrics": [
                            {
                                "name": "任务完成率",
                                "init": 78,
                                "best": 84,
                                "delta": 6,
                                "unit": "%",
                            },
                        ],
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
