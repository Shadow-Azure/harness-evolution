"""Deterministic six-step corpus: fixture loading, seeding, and run rows.

Shared by the `m5-06-six-step-api` tests; lives directly under `tests/` because
the issue's dashed directory name cannot be a Python package.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy import delete, func, insert, select

from app.db.base import Database
from app.db.crud.fixtures import ensure_fixture_external_tables
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

NOW = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)
SESSION_ID = "050b81ba-0000-4000-8000-0000000000c3"
CASE_ID = "bc-050b-03"
PROBE_ID = "pr-050b-03"
RUN_ID = "evo-20261023-01"
CLUSTER_ID = "C1"
ROUND_ID = "r-01"

_FIXTURE_DIR = Path(__file__).parent / "m5-06-six-step-api" / "fixtures"
_SNAPSHOT_DIR = Path(__file__).parent / "m5-06-six-step-api" / "snapshots"


def load_fixture(step: str) -> dict[str, Any]:
    """Return one of the six fixture groups shaped after 05 §3.6.1."""
    return _load_json(_FIXTURE_DIR / f"step-{step}.json")


def load_snapshot(step: str) -> dict[str, Any]:
    """Return the expected 200 response body for one step endpoint."""
    return _load_json(_SNAPSHOT_DIR / f"step-{step}.json")


def _load_json(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON document from the test corpus."""
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _session_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Build one session-family row with deterministic defaults."""
    started = datetime.fromisoformat(entry["startedAt"])
    return {
        "id": entry["id"],
        "short_title": entry["title"],
        "title": entry["title"],
        "search_text": entry["title"],
        "repo_name": "example/repo",
        "project_path": "/workspace/example",
        "model": entry["model"],
        "models": [entry["model"]],
        "started_at": started,
        "ended_at": started,
        "duration_seconds": 1,
        "status": "completed",
        "skill_names": [],
        "user_turns_count": 1,
        "messages_count": 1,
        "tools_count": 0,
        "errors_count": 0,
        "agents_count": 1,
        "tokens_total": 1,
        "source_type": "synthetic",
        "main_record_id": None,
        "imported_at": NOW,
        "updated_at": NOW,
    }


def _case_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Build one bad-case row reported against the self-evolved object."""
    return {
        "bad_case_id": entry["badCaseId"],
        "bad_case_session_id": entry["sessionId"],
        "bad_case_type": entry.get("badCaseType", "discovery"),
        "object_name": entry["objectName"],
        "object_type": entry.get("objectType", "skill"),
        "object_version": entry.get("objectVersion"),
        "bad_case_agent_id": entry.get("badCaseAgentId"),
        "title": entry["title"],
        "bad_case_description": entry["reason"],
        "meta_data": {},
        "source": "fixtures",
        "created_at": NOW,
        "updated_at": NOW,
    }


def _probe_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Build one root-cause probe row owned by the analyzed object."""
    return {
        "probe_id": entry["probeId"],
        "session_id": entry["sessionId"],
        "probe_type": entry.get("probeType", "skill"),
        "probe_object": entry["probeObject"],
        "object_version": entry.get("objectVersion"),
        "attribute_type": entry["attributeType"],
        "probe_description": entry["probeDescription"],
        "probe_analysis": entry["probeAnalysis"],
        "created_at": NOW,
        "updated_at": NOW,
    }


def _analysis_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Build one attribution row linking a bad case to its probe."""
    return {
        "bad_case_id": entry["badCaseId"],
        "analysis_status": entry["analysisStatus"],
        "probe_id": entry.get("probeId"),
        "analysis_result": entry.get("analysisResult"),
        "updated_at": NOW,
    }


def _run_row(entry: dict[str, Any]) -> dict[str, Any]:
    """Build one evolution run row from a fixture snapshot."""
    mode = entry.get("mode", "full")
    window_from = entry.get("windowFrom")
    window_to = entry.get("windowTo")
    return {
        "id": entry["id"],
        "title": entry.get("title", f"{entry['targetName']} {entry['targetVersion']} 自进化"),
        "mode": mode,
        "engine_key": entry.get("engineKey", mode),
        "eval_config": entry.get("evalConfig", {}),
        "target_config_id": entry.get("targetConfigId"),
        "target_type": entry["targetType"],
        "target_name": entry["targetName"],
        "target_version": entry["targetVersion"],
        "repo_url": entry.get("repoUrl", "https://git.example.com/agent-skills.git"),
        "sub_dir": entry.get("subDir", "skills/deep-research"),
        "remote_name": "origin",
        "push_status": entry.get("pushStatus", "pending"),
        "window_from": date.fromisoformat(window_from) if window_from else None,
        "window_to": date.fromisoformat(window_to) if window_to else None,
        "models": entry.get("models", []),
        "status": entry["status"],
        "blocked_stage": entry.get("blockedStage"),
        "retry_attempts": entry.get("retryAttempts", 0),
        "eval_status": entry.get("evalStatus", "pending"),
        "progress_unit": entry["progressUnit"],
        "stats": entry.get("stats", {}),
        "created_by": None,
        "created_at": NOW,
    }


def _cluster_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the persisted cluster rows of one fixture group."""
    return [
        {
            "probe_cluster_id": cluster["probeClusterId"],
            "run_id": data["run"]["id"],
            "seq": cluster["seq"],
            "probe_cluster_description": cluster["description"],
            "probe_cluster_type": cluster["type"],
            "confidence": cluster.get("confidence"),
            "impact": cluster.get("impact"),
            "severity": cluster.get("severity"),
            "rank": cluster.get("rank"),
            "created_at": NOW,
        }
        for cluster in data.get("clusters", [])
    ]


def _link_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the cluster-to-probe link rows of one fixture group."""
    return [
        {"probe_cluster_id": link["probeClusterId"], "probe_id": probe_id}
        for link in data.get("clusterProbes", [])
        for probe_id in link["probeIds"]
    ]


def _round_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the execution round rows of one fixture group."""
    rows: list[dict[str, Any]] = []
    for round_ in data.get("rounds", []):
        candidate = round_.get("candidate") or {}
        push = round_.get("push") or {}
        evaluation = round_.get("eval") or {}
        final_commit = round_.get("finalCommit") or {}
        rows.append(
            {
                "id": round_["id"],
                "run_id": data["run"]["id"],
                "probe_cluster_id": round_["probeClusterId"],
                "seq": round_["seq"],
                "status": round_["status"],
                "patch": round_.get("patch"),
                "candidate_ref": candidate.get("ref"),
                "candidate_commit": candidate.get("commit"),
                "candidate_message": candidate.get("message"),
                "push_status": push.get("status", "pending"),
                "push_attempts": push.get("attempts", 0),
                "push_error": push.get("error"),
                "eval_status": evaluation.get("status", "pending"),
                "eval_current": evaluation.get("current"),
                "eval_candidate": evaluation.get("candidate"),
                "eval_next_poll_at": evaluation.get("nextPollAt"),
                "accepted": round_.get("accepted", False),
                "commit_hash": final_commit.get("hash"),
                "commit_message": final_commit.get("message"),
            },
        )
    return rows


async def seed_external_corpus(database: Database) -> None:
    """Insert the shared external problem corpus (session, case, probe, analysis).

    The corpus rows are identical across fixture groups, so repeated calls
    skip existing identities and several groups can share one database.
    """
    await ensure_fixture_external_tables(database)
    async with database.transaction() as session:
        session_exists = (
            await session.execute(
                select(session_families.c.id).where(session_families.c.id == SESSION_ID),
            )
        ).scalar_one_or_none()
        if session_exists is not None:
            return
        source_id = (
            int(
                (
                    await session.execute(
                        select(func.coalesce(func.max(source_records.c.id), 0)),
                    )
                ).scalar_one(),
            )
            + 1
        )
        await session.execute(
            insert(source_records),
            {
                "id": source_id,
                "root_session_id": SESSION_ID,
                "agent_id": SESSION_ID,
                "kind": "main",
                "source_type": "synthetic",
                "line_count": 1,
                "received_at": NOW,
            },
        )
        await session.execute(
            insert(session_families),
            {
                **_session_row(
                    {
                        "id": SESSION_ID,
                        "title": "研究'用户数据驱动自进化'提到的所有方法",
                        "model": "glm-5.3",
                        "startedAt": "2026-09-05T17:17:53+08:00",
                    },
                ),
                "main_record_id": source_id,
            },
        )
        await session.execute(
            insert(bad_cases),
            [
                _case_row(
                    {
                        "badCaseId": CASE_ID,
                        "sessionId": SESSION_ID,
                        "badCaseType": "discovery",
                        "objectName": "deep-research",
                        "objectVersion": "v2.0.0",
                        "title": "检索索引读取失败",
                        "reason": "deep-research skill发现前置步骤存在问题：检索索引读取失败",  # noqa: RUF001
                    },
                ),
            ],
        )
        await session.execute(
            insert(probe_reports),
            [
                _probe_row(
                    {
                        "probeId": PROBE_ID,
                        "sessionId": SESSION_ID,
                        "probeObject": "deep-research",
                        "objectVersion": "v2.0.0",
                        "attributeType": "error",
                        "probeDescription": "检索索引读取失败",
                        "probeAnalysis": "在对象逻辑中复现并确认索引未校验",
                    },
                ),
            ],
        )
        await session.execute(
            insert(bad_case_analysis),
            [
                _analysis_row(
                    {
                        "badCaseId": CASE_ID,
                        "analysisStatus": "analyzed_issue",
                        "probeId": PROBE_ID,
                        "analysisResult": {"summary": "检索索引读取失败，属于对象自身错误"},  # noqa: RUF001
                    },
                ),
            ],
        )


async def seed_run(
    database: Database,
    *,
    progress_unit: int,
    status: str = "running",
    mode: str = "full",
    run_id: str = RUN_ID,
) -> None:
    """Insert the canonical six-step run row in one deterministic state."""
    async with database.transaction() as session:
        await session.execute(
            insert(evolution_runs),
            _run_row(
                {
                    "id": run_id,
                    "mode": mode,
                    "engineKey": mode,
                    "targetType": "skill",
                    "targetName": "deep-research",
                    "targetVersion": "v2.0.0",
                    "windowFrom": "2026-08-20",
                    "windowTo": "2026-09-10",
                    "models": ["glm-5.3"],
                    "status": status,
                    "progressUnit": progress_unit,
                },
            ),
        )


async def clear_evolution_state(database: Database) -> None:
    """Delete one database's evolution-run state between fixture groups."""
    async with database.transaction() as session:
        for table in (
            probe_cluster_probes,
            evolution_rounds,
            probe_clusters,
            evolution_finals,
            evolution_runs,
        ):
            await session.execute(delete(table))


async def seed_fixture(database: Database, data: dict[str, Any]) -> None:
    """Insert one complete fixture group in dependency order."""
    await seed_external_corpus(database)
    async with database.transaction() as session:
        await session.execute(insert(evolution_runs), _run_row(data["run"]))
        if data.get("clusters"):
            await session.execute(insert(probe_clusters), _cluster_rows(data))
        if data.get("clusterProbes"):
            await session.execute(insert(probe_cluster_probes), _link_rows(data))
        if data.get("rounds"):
            await session.execute(insert(evolution_rounds), _round_rows(data))
        final = data.get("final")
        if final is not None:
            await session.execute(
                insert(evolution_finals).values(
                    run_id=data["run"]["id"],
                    best_version=final["bestVersion"],
                    verdict=final["verdict"],
                    best_score=final["bestScore"],
                    init_score=final["initScore"],
                    metrics=final.get("metrics", []),
                ),
            )
