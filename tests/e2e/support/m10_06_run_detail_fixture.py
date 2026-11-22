"""Insert deterministic V2 and legacy seven-step runs for the M10-06 browser smoke."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, insert, select

from app.config import Settings
from app.db.factory import create_database
from app.db.models.domain import (
    agents,
    bad_case_analysis,
    bad_cases,
    probe_reports,
    session_families,
    source_records,
)
from app.db.models.evolution import (
    evolution_finals,
    evolution_rounds,
    evolution_run_candidates,
    evolution_runs,
    probe_cluster_probes,
    probe_clusters,
)
from app.db.models.run_events import evolution_run_events
from app.db.models.users import users
from app.db.models.workspace import DEFAULT_WORKSPACE_ID

BASE = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
LONG_SESSION_PROMPT = ("SWE-bench astropy-12907 修复任务 " * 200)[:3337]
ACCEPTED_COMMIT_MESSAGE = """evolve(deep-research@v2.0.0): 修复检索索引未校验导致的越界读取

## 问题

聚类「检索索引读取失败」包含 3 个来源 bad case：BC-HC-0007、BC-HC-0011、BC-HC-0014。读取索引前未校验快照字段，遇到旧快照时会越界读取。

## 分析

deep-research@v2.0.0 默认假设快照字段完整，但历史快照可能缺少 `chunk_count`。复现输入见追溯段的链接。

## 改动

- `SKILL.md`：读取索引前校验 `chunk_count` 与 `doc_count`
- 补充边界测试，覆盖旧快照
- 失败时返回可诊断的错误信息

## 追溯

- 自进化运行：EV-20261109-01
- 问题簇：C1 检索索引读取失败
- https://example.com/badcases/BC-HC-0007
- 来源问题：BC-HC-0007、BC-HC-0011

---

Harness-Evaluated-Commit: ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12
Harness-Verdict: accepted (88.9 vs 84.3, +4.6)
Harness-Decision-Rule: external-verdict
"""
RUN_IDS = (
    "run-v2-completed",
    "run-v2-blocked-attribution",
    "run-v2-legacy",
    "run-v2-preparing",
)
CASE_IDS = tuple(f"v2-case-{index}" for index in range(1, 7)) + (
    "v2-blocked-case-1",
    "v2-legacy-case-1",
)
PROBE_IDS = tuple(f"v2-probe-{index}" for index in range(1, 7)) + (
    "v2-blocked-probe-1",
    "v2-legacy-probe-1",
)
SESSION_IDS = tuple(f"v2-session-{index}" for index in range(1, 6)) + (
    "v2-blocked-session-1",
    "v2-legacy-session-1",
)


def _run(
    run_id: str,
    *,
    status: str,
    progress_unit: int,
    attribution_engine: str,
    stats: dict[str, Any],
    created_by: str,
    blocked_stage: str | None = None,
    error: tuple[str, str] | None = None,
    retry_attempts: int = 0,
    next_retry_at: datetime | None = None,
) -> dict[str, Any]:
    """Build one deterministic run row with a complete config snapshot."""
    created_at = BASE - timedelta(minutes=RUN_IDS.index(run_id) * 10)
    return {
        "id": run_id,
        "workspace_id": DEFAULT_WORKSPACE_ID,
        "title": f"{run_id} 自进化",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {},
        "potential_policy": {"preset": "default"},
        "cache_enabled": True,
        "attribution_engine": attribution_engine,
        "target_config_id": None,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "validation_project_id": "val-deep-research",
        "test_project_id": "test-deep-research",
        "repo_path": None,
        "base_ref": "v2.0.0",
        "base_commit": "9f3c2a1d8e7b6c5a4f3e2d1c0b9a8f7e6d5c4b3a",
        "branch_name": f"evo/{run_id}",
        "workspace_path": None,
        "remote_name": "origin",
        "push_status": "succeeded",
        "pushed_at": created_at + timedelta(minutes=1),
        "push_error": None,
        "window_from": date(2026, 9, 1),
        "window_to": date(2026, 10, 20),
        "models": ["glm-5.3"],
        "status": status,
        "blocked_stage": blocked_stage,
        "retry_attempts": retry_attempts,
        "next_retry_at": next_retry_at,
        "eval_status": "completed" if status == "completed" else "pending",
        "error_stage": error[0] if error else None,
        "error_message": error[1] if error else None,
        "error_at": created_at + timedelta(minutes=2) if error else None,
        "progress_unit": progress_unit,
        "stats": stats,
        "created_by": created_by,
        "created_at": created_at,
        "finished_at": created_at + timedelta(minutes=8)
        if status in {"completed", "failed", "interrupted"}
        else None,
    }


async def main() -> None:
    """Replace the M10-06 fixture rows in every table the detail reads."""
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
            await session.execute(
                delete(evolution_run_events).where(
                    evolution_run_events.c.run_id.in_(RUN_IDS),
                ),
            )
            await session.execute(
                delete(evolution_finals).where(
                    evolution_finals.c.run_id.in_(RUN_IDS),
                ),
            )
            await session.execute(
                delete(evolution_rounds).where(
                    evolution_rounds.c.run_id.in_(RUN_IDS),
                ),
            )
            await session.execute(
                delete(evolution_run_candidates).where(
                    evolution_run_candidates.c.run_id.in_(RUN_IDS),
                ),
            )
            await session.execute(
                delete(probe_cluster_probes).where(
                    probe_cluster_probes.c.probe_cluster_id.like("v2-%"),
                ),
            )
            await session.execute(
                delete(probe_clusters).where(
                    probe_clusters.c.run_id.in_(RUN_IDS),
                ),
            )
            await session.execute(
                delete(evolution_runs).where(evolution_runs.c.id.in_(RUN_IDS)),
            )
            await session.execute(
                delete(bad_case_analysis).where(
                    bad_case_analysis.c.bad_case_id.in_(CASE_IDS),
                ),
            )
            await session.execute(
                delete(bad_cases).where(bad_cases.c.bad_case_id.in_(CASE_IDS)),
            )
            await session.execute(
                delete(probe_reports).where(probe_reports.c.probe_id.in_(PROBE_IDS)),
            )
            await session.execute(
                delete(agents).where(agents.c.root_session_id.in_(SESSION_IDS)),
            )
            await session.execute(
                delete(session_families).where(session_families.c.id.in_(SESSION_IDS)),
            )
            await session.execute(
                delete(source_records).where(
                    source_records.c.root_session_id.in_(SESSION_IDS),
                ),
            )

            base_stats = {
                "sessions": 5,
                "versionUnresolvedSessions": 1,
                "badCases": 6,
                "potential": 6,
                "attributed": 5,
                "reused": 2,
                "clusters": 2,
                "byCategory": {"model": 1, "prompt": 1, "error": 3},
                "reportedSessions": 7,
                "skippedSessions": 2,
                "pendingSessions": 0,
                "byReason": {
                    "self_report": 3,
                    "after_object": 2,
                    "both": 1,
                    "policy_excluded": 0,
                    "order_unknown": 0,
                },
                "sessionRows": [
                    {
                        "sessionId": "v2-session-1",
                        "title": LONG_SESSION_PROMPT,
                        "short": "来源运行 A",
                        "objectTriggerAt": "2026-10-01T09:30:00+08:00",
                        "badCaseCount": 2,
                        "potentialCount": 2,
                    },
                    {
                        "sessionId": "v2-session-2",
                        "title": "来源运行 B",
                        "short": "来源运行 B",
                        "objectTriggerAt": "2026-10-02T10:00:00+08:00",
                        "badCaseCount": 1,
                        "potentialCount": 1,
                    },
                    {
                        "sessionId": "v2-session-3",
                        "title": "来源运行 C",
                        "short": "来源运行 C",
                        "objectTriggerAt": "2026-10-03T11:00:00+08:00",
                        "badCaseCount": 1,
                        "potentialCount": 1,
                    },
                    {
                        "sessionId": "v2-session-4",
                        "title": "来源运行 D",
                        "short": "来源运行 D",
                        "objectTriggerAt": "2026-10-04T12:00:00+08:00",
                        "badCaseCount": 1,
                        "potentialCount": 1,
                    },
                    {
                        "sessionId": "v2-session-5",
                        "title": "来源运行 E",
                        "short": "来源运行 E",
                        "objectTriggerAt": "2026-10-05T13:00:00+08:00",
                        "badCaseCount": 1,
                        "potentialCount": 1,
                    },
                ],
            }
            blocked_stats = {
                "sessions": 1,
                "versionUnresolvedSessions": 0,
                "badCases": 1,
                "potential": 1,
                "attributed": 1,
                "reused": 0,
                "clusters": 0,
                "byCategory": {"model": 0, "prompt": 0, "error": 1},
                "reportedSessions": 1,
                "skippedSessions": 0,
                "pendingSessions": 0,
                "byReason": {
                    "self_report": 1,
                    "after_object": 0,
                    "both": 0,
                    "policy_excluded": 0,
                    "order_unknown": 0,
                },
            }
            legacy_stats = {
                "sessions": 1,
                "probes": 1,
                "usedProbes": 1,
                "clusters": 1,
                "byAttributeType": {"model": 0, "prompt": 0, "error": 1, "nonIssue": 0},
            }
            await session.execute(
                insert(evolution_runs),
                [
                    _run(
                        "run-v2-completed",
                        status="completed",
                        progress_unit=8,
                        attribution_engine="rule-v1",
                        stats=base_stats,
                        created_by=admin_id,
                    ),
                    _run(
                        "run-v2-blocked-attribution",
                        status="blocked",
                        progress_unit=3,
                        attribution_engine="rule-v1",
                        stats=blocked_stats,
                        created_by=admin_id,
                        blocked_stage="attribution",
                        error=("attribution", "归因引擎暂时不可用"),
                        retry_attempts=2,
                        next_retry_at=BASE + timedelta(hours=2),
                    ),
                    _run(
                        "run-v2-legacy",
                        status="completed",
                        progress_unit=6,
                        attribution_engine="legacy-probe-import",
                        stats=legacy_stats,
                        created_by=admin_id,
                    ),
                    _run(
                        "run-v2-preparing",
                        status="preparing",
                        progress_unit=0,
                        attribution_engine="rule-v1",
                        stats={
                            "sessions": 0,
                            "versionUnresolvedSessions": 0,
                            "badCases": 0,
                            "potential": 0,
                            "attributed": 0,
                            "reused": 0,
                            "clusters": 0,
                            "byCategory": {"model": 0, "prompt": 0, "error": 0},
                        },
                        created_by=admin_id,
                    ),
                ],
            )

            source_rows: list[dict[str, Any]] = []
            session_rows: list[dict[str, Any]] = []
            agent_rows: list[dict[str, Any]] = []
            bad_case_rows: list[dict[str, Any]] = []
            probe_rows: list[dict[str, Any]] = []
            analysis_rows: list[dict[str, Any]] = []
            next_source_id = int(
                (
                    await session.execute(
                        select(func.coalesce(func.max(source_records.c.id), 0)),
                    )
                ).scalar_one(),
            )
            for offset, session_id in enumerate(SESSION_IDS, start=1):
                next_source_id += 1
                source_rows.append(
                    {
                        "id": next_source_id,
                        "root_session_id": session_id,
                        "agent_id": session_id,
                        "kind": "main",
                        "source_type": "synthetic",
                        "line_count": 1,
                        "received_at": BASE,
                    },
                )
                session_rows.append(
                    {
                        "id": session_id,
                        "short_title": f"来源运行 {session_id}",
                        "title": f"来源运行 {session_id}",
                        "search_text": f"来源运行 {session_id}",
                        "repo_name": "example/repo",
                        "project_path": "/workspace/example",
                        "model": "glm-5.3",
                        "models": ["glm-5.3"],
                        "started_at": BASE,
                        "ended_at": BASE,
                        "duration_seconds": 1,
                        "status": "partial",
                        "skill_names": ["deep-research"],
                        "user_turns_count": 1,
                        "messages_count": 1,
                        "tools_count": 0,
                        "errors_count": 1,
                        "agents_count": 1,
                        "tokens_total": 1,
                        "source_type": "synthetic",
                        "main_record_id": next_source_id,
                        "imported_at": BASE,
                        "updated_at": BASE,
                    },
                )
                agent_rows.append(
                    {
                        "id": session_id,
                        "root_session_id": session_id,
                        "parent_agent_id": None,
                        "kind": "main",
                        "model": "glm-5.3",
                        "spawn_depth": 0,
                        "transcript_record_id": next_source_id,
                        "lines": 1,
                        "messages_count": 1,
                        "tokens_total": 1,
                        "tools_count": 0,
                        "errors_count": 1,
                        "meta": None,
                        "sort_key": 0.0,
                    },
                )
            await session.execute(insert(source_records), source_rows)
            await session.execute(insert(session_families), session_rows)
            await session.execute(insert(agents), agent_rows)

            cases = [
                ("v2-case-1", "v2-session-1", "检索索引读取失败", "self"),
                ("v2-case-2", "v2-session-2", "输出缺少来源引用", "self"),
                ("v2-case-3", "v2-session-1", "分块越界导致上下文丢失", "discovery"),
                ("v2-case-4", "v2-session-3", "检索结果未去重", "self"),
                ("v2-case-5", "v2-session-4", "缓存命中后未刷新", "discovery"),
                ("v2-case-6", "v2-session-5", "另一个对象的问题", "discovery"),
                ("v2-blocked-case-1", "v2-blocked-session-1", "归因阶段阻塞的来源问题", "self"),
                ("v2-legacy-case-1", "v2-legacy-session-1", "历史六步问题", "self"),
            ]
            for case_id, session_id, title, case_type in cases:
                bad_case_rows.append(
                    {
                        "bad_case_id": case_id,
                        "workspace_id": DEFAULT_WORKSPACE_ID,
                        "bad_case_session_id": session_id,
                        "bad_case_type": case_type,
                        "object_name": "deep-research",
                        "object_type": "skill",
                        "object_version": "v2.0.0",
                        "bad_case_agent_id": session_id,
                        "title": title,
                        "bad_case_description": title,
                        "meta_data": {},
                        "source": "fixtures",
                        "created_at": BASE,
                        "updated_at": BASE,
                    },
                )
            await session.execute(insert(bad_cases), bad_case_rows)

            probes = [
                ("v2-probe-1", "v2-session-1", "v2-case-1", "error", "attributed", 0.82, 1),
                ("v2-probe-2", "v2-session-2", "v2-case-2", "prompt", "attributed", 0.74, 2),
                ("v2-probe-3", "v2-session-1", "v2-case-3", "error", "attributed", 0.82, 1),
                ("v2-probe-4", "v2-session-3", "v2-case-4", "error", "attributed", 0.82, 1),
                ("v2-probe-5", "v2-session-4", "v2-case-5", "model", "attributed", 0.66, 2),
                ("v2-probe-6", "v2-session-5", "v2-case-6", None, "non_target", 0.4, 1),
                (
                    "v2-blocked-probe-1",
                    "v2-blocked-session-1",
                    "v2-blocked-case-1",
                    "error",
                    "attributed",
                    0.8,
                    1,
                ),
                (
                    "v2-legacy-probe-1",
                    "v2-legacy-session-1",
                    "v2-legacy-case-1",
                    "error",
                    "attributed",
                    0.8,
                    1,
                ),
            ]
            for probe_id, session_id, case_id, attribute_type, conclusion, confidence, reused in probes:
                probe_rows.append(
                    {
                        "probe_id": probe_id,
                        "workspace_id": DEFAULT_WORKSPACE_ID,
                        "session_id": session_id,
                        "probe_type": "skill",
                        "probe_object": "deep-research",
                        "object_version": "v2.0.0",
                        "attribute_type": attribute_type,
                        "conclusion": conclusion,
                        "confidence": confidence,
                        "probe_description": f"{case_id} 的归因结论",
                        "probe_analysis": f"**确认问题**\n\n- {case_id}",
                        "policy_version": "v1",
                        "attribution_engine": (
                            "legacy-probe-import"
                            if probe_id.startswith("v2-legacy")
                            else "rule-v1"
                        ),
                        "created_run_id": None,
                        "last_reused_run_id": None,
                        "reused_count": reused,
                        "created_at": BASE,
                        "updated_at": BASE,
                    },
                )
                analysis_rows.append(
                    {
                        "bad_case_id": case_id,
                        "analysis_status": (
                            "analyzed_nonissue"
                            if conclusion == "non_target"
                            else "analyzed_issue"
                        ),
                        "probe_id": probe_id,
                        "analysis_result": {"summary": f"{case_id} 的归因结论"},
                        "updated_at": BASE,
                    },
                )
            await session.execute(insert(probe_reports), probe_rows)
            await session.execute(insert(bad_case_analysis), analysis_rows)

            candidate_rows = [
                (
                    "v2-candidate-1",
                    "v2-case-1",
                    "v2-session-1",
                    "v2-probe-1",
                    "comparable",
                    "self_report",
                    True,
                ),
                (
                    "v2-candidate-2",
                    "v2-case-2",
                    "v2-session-2",
                    "v2-probe-2",
                    "comparable",
                    "self_report",
                    False,
                ),
                (
                    "v2-candidate-3",
                    "v2-case-3",
                    "v2-session-1",
                    "v2-probe-3",
                    "comparable",
                    "after_object",
                    False,
                ),
                (
                    "v2-candidate-4",
                    "v2-case-4",
                    "v2-session-3",
                    "v2-probe-4",
                    "comparable",
                    "after_object",
                    True,
                ),
                (
                    "v2-candidate-5",
                    "v2-case-5",
                    "v2-session-4",
                    "v2-probe-5",
                    "unknown",
                    "order_unknown",
                    False,
                ),
                (
                    "v2-candidate-6",
                    "v2-case-6",
                    "v2-session-5",
                    "v2-probe-6",
                    "comparable",
                    "self_report",
                    False,
                ),
                (
                    "v2-blocked-candidate-1",
                    "v2-blocked-case-1",
                    "v2-blocked-session-1",
                    "v2-blocked-probe-1",
                    "comparable",
                    "self_report",
                    False,
                ),
            ]
            candidate_values = []
            for (
                candidate_id,
                case_id,
                session_id,
                probe_id,
                order_state,
                included_reason,
                cached,
            ) in candidate_rows:
                candidate_values.append(
                    {
                        "id": candidate_id,
                        "run_id": "run-v2-blocked-attribution"
                        if candidate_id.startswith("v2-blocked")
                        else "run-v2-completed",
                        "workspace_id": DEFAULT_WORKSPACE_ID,
                        "session_id": session_id,
                        "bad_case_id": case_id,
                        "object_trigger_agent_id": session_id,
                        "object_trigger_event_index": 0,
                        "object_trigger_at": BASE,
                        "case_trigger_agent_id": session_id,
                        "case_trigger_event_index": 1,
                        "case_trigger_at": BASE + timedelta(minutes=1),
                        "order_state": order_state,
                        "included": True,
                        "included_reason": included_reason,
                        "probe_id": probe_id,
                        "is_cached": cached,
                        "created_at": BASE,
                    },
                )
            await session.execute(insert(evolution_run_candidates), candidate_values)

            cluster_rows = [
                {
                    "probe_cluster_id": "v2-cluster-1",
                    "run_id": "run-v2-completed",
                    "seq": 1,
                    "probe_cluster_description": "3 个 bad case 共同表现：检索索引读取失败",
                    "probe_cluster_type": "error",
                    "confidence": 0.82,
                    "impact": 9,
                    "severity": 9.1,
                    "rank": 1,
                    "created_at": BASE,
                },
                {
                    "probe_cluster_id": "v2-cluster-2",
                    "run_id": "run-v2-completed",
                    "seq": 2,
                    "probe_cluster_description": "2 个 bad case 共同表现：输出缺少来源引用",
                    "probe_cluster_type": "prompt",
                    "confidence": 0.74,
                    "impact": 7,
                    "severity": 7.8,
                    "rank": 2,
                    "created_at": BASE,
                },
                {
                    "probe_cluster_id": "v2-legacy-cluster-1",
                    "run_id": "run-v2-legacy",
                    "seq": 1,
                    "probe_cluster_description": "历史六步问题簇",
                    "probe_cluster_type": "error",
                    "confidence": 0.82,
                    "impact": 9,
                    "severity": 7.4,
                    "rank": 1,
                    "created_at": BASE,
                },
            ]
            await session.execute(insert(probe_clusters), cluster_rows)
            await session.execute(
                insert(probe_cluster_probes),
                [
                    {"probe_cluster_id": "v2-cluster-1", "probe_id": "v2-probe-1"},
                    {"probe_cluster_id": "v2-cluster-1", "probe_id": "v2-probe-3"},
                    {"probe_cluster_id": "v2-cluster-1", "probe_id": "v2-probe-4"},
                    {"probe_cluster_id": "v2-cluster-2", "probe_id": "v2-probe-2"},
                    {"probe_cluster_id": "v2-cluster-2", "probe_id": "v2-probe-5"},
                    {"probe_cluster_id": "v2-legacy-cluster-1", "probe_id": "v2-legacy-probe-1"},
                ],
            )

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
            round_rows = [
                {
                    **round_defaults,
                    "id": "v2-round-1",
                    "run_id": "run-v2-completed",
                    "probe_cluster_id": "v2-cluster-1",
                    "seq": 1,
                    "status": "accepted",
                    "patch": {
                        "file": "SKILL.md",
                        "lines": ["@@ -1 +1 @@", "- 读取索引", "+ 读取索引前校验快照字段"],
                    },
                    "candidate_ref": "evo/run-v2-completed/candidate/r1",
                    "candidate_commit": "ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12",
                    "candidate_message": "evolve(deep-research): 校验快照字段",
                    "push_status": "succeeded",
                    "push_attempts": 1,
                    "pushed_at": BASE,
                    "eval_status": "completed",
                    "eval_attempts": 1,
                    "eval_current": 84.3,
                    "eval_candidate": 88.9,
                    "accepted": True,
                    "commit_hash": "ef56ab12cd34ef56ab12cd34ef56ab12cd34ef56",
                    "commit_message": ACCEPTED_COMMIT_MESSAGE,
                },
                {
                    **round_defaults,
                    "id": "v2-round-2",
                    "run_id": "run-v2-completed",
                    "probe_cluster_id": "v2-cluster-2",
                    "seq": 2,
                    "status": "rejected",
                    "patch": {
                        "file": "SKILL.md",
                        "lines": ["@@ -8 +8 @@", "- 引用可选", "+ 引用必须可溯源"],
                    },
                    "candidate_ref": "evo/run-v2-completed/candidate/r2",
                    "candidate_commit": "cd34ab12ef56cd34ab12ef56cd34ab12ef56cd34",
                    "candidate_message": "evolve(deep-research): 来源引用校验",
                    "push_status": "succeeded",
                    "push_attempts": 1,
                    "pushed_at": BASE,
                    "eval_status": "completed",
                    "eval_attempts": 1,
                    "eval_current": 88.9,
                    "eval_candidate": 88.1,
                    "accepted": False,
                },
                {
                    **round_defaults,
                    "id": "v2-legacy-round-1",
                    "run_id": "run-v2-legacy",
                    "probe_cluster_id": "v2-legacy-cluster-1",
                    "seq": 1,
                    "status": "accepted",
                    "push_status": "succeeded",
                    "push_attempts": 1,
                    "eval_status": "completed",
                    "eval_attempts": 1,
                    "eval_current": 80.1,
                    "eval_candidate": 82.2,
                    "accepted": True,
                    "commit_hash": "1212ab12cd34ef56ab12cd34ef56ab12cd34ef56",
                    "commit_message": "evolve(deep-research): 历史问题",
                },
            ]
            await session.execute(insert(evolution_rounds), round_rows)
            await session.execute(
                insert(evolution_finals),
                [
                    {
                        "run_id": "run-v2-completed",
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
                        "run_id": "run-v2-legacy",
                        "best_version": "v2.0.0",
                        "verdict": False,
                        "best_score": 80.1,
                        "init_score": 80.1,
                        "metrics": [],
                    },
                ],
            )

            event_rows = [
                {
                    "run_id": "run-v2-completed",
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "seq": 1,
                    "event_type": "run_created",
                    "level": "info",
                    "stage": "step",
                    "step_index": 0,
                    "cluster_id": None,
                    "evolution_round_id": None,
                    "job_id": "job-v2-completed",
                    "message": "运行已受理",
                    "payload": None,
                    "error_type": None,
                    "error_message": None,
                    "error_detail": None,
                    "created_at": BASE,
                },
                {
                    "run_id": "run-v2-completed",
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "seq": 2,
                    "event_type": "sessions_linked",
                    "level": "info",
                    "stage": "step",
                    "step_index": 1,
                    "cluster_id": None,
                    "evolution_round_id": None,
                    "job_id": "job-v2-completed",
                    "message": "已关联 5 个 Session",
                    "payload": {"durationMs": 120},
                    "error_type": None,
                    "error_message": None,
                    "error_detail": None,
                    "created_at": BASE + timedelta(seconds=1),
                },
                {
                    "run_id": "run-v2-completed",
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "seq": 3,
                    "event_type": "potential_computed",
                    "level": "info",
                    "stage": "step",
                    "step_index": 2,
                    "cluster_id": None,
                    "evolution_round_id": None,
                    "job_id": "job-v2-completed",
                    "message": "潜在 bad case 计算完成",
                    "payload": {"durationMs": 300},
                    "error_type": None,
                    "error_message": None,
                    "error_detail": None,
                    "created_at": BASE + timedelta(seconds=2),
                },
                {
                    "run_id": "run-v2-completed",
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "seq": 4,
                    "event_type": "attribution_created",
                    "level": "warn",
                    "stage": "step",
                    "step_index": 3,
                    "cluster_id": None,
                    "evolution_round_id": None,
                    "job_id": "job-v2-completed",
                    "message": "归因引擎返回部分结论",
                    "payload": {"durationMs": 800},
                    "error_type": "AttributionWarning",
                    "error_message": "部分候选未返回结论",
                    "error_detail": "token=<redacted>\nAuthorization: Bearer <redacted>",
                    "created_at": BASE + timedelta(seconds=3),
                },
                {
                    "run_id": "run-v2-completed",
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "seq": 5,
                    "event_type": "clusters_created",
                    "level": "info",
                    "stage": "cluster",
                    "step_index": 4,
                    "cluster_id": "v2-cluster-1",
                    "evolution_round_id": None,
                    "job_id": "job-v2-completed",
                    "message": "已生成 2 个问题簇",
                    "payload": {"durationMs": 90},
                    "error_type": None,
                    "error_message": None,
                    "error_detail": None,
                    "created_at": BASE + timedelta(seconds=4),
                },
                {
                    "run_id": "run-v2-completed",
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "seq": 6,
                    "event_type": "candidate_committed",
                    "level": "info",
                    "stage": "candidate",
                    "step_index": 5,
                    "cluster_id": "v2-cluster-1",
                    "evolution_round_id": "v2-round-1",
                    "job_id": "job-v2-completed",
                    "message": "候选 commit 已生成",
                    "payload": {"durationMs": 50},
                    "error_type": None,
                    "error_message": None,
                    "error_detail": None,
                    "created_at": BASE + timedelta(seconds=5),
                },
                {
                    "run_id": "run-v2-blocked-attribution",
                    "workspace_id": DEFAULT_WORKSPACE_ID,
                    "seq": 1,
                    "event_type": "run_blocked",
                    "level": "error",
                    "stage": "step",
                    "step_index": 3,
                    "cluster_id": None,
                    "evolution_round_id": None,
                    "job_id": "job-v2-blocked",
                    "message": "归因引擎暂时不可用",
                    "payload": None,
                    "error_type": "AttributionUnavailable",
                    "error_message": "归因引擎暂时不可用",
                    "error_detail": "retry token=<redacted>",
                    "created_at": BASE + timedelta(minutes=2),
                },
            ]
            await session.execute(insert(evolution_run_events), event_rows)
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
