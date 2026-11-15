"""Shared ids and fixture types for the latest-ten workspace session tests."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.db.base import Database
from app.utils.time import now_shanghai

SHANGHAI = timezone(timedelta(hours=8))

SESSION_IDS = tuple(f"10000000-0000-4000-8000-{index:012d}" for index in range(1, 14))
WORKSPACE_A_ROOTS = SESSION_IDS[:12]
REMOTE_ROOT = SESSION_IDS[12]
PENDING_ROOT = "30000000-0000-4000-8000-000000000099"
LATEST_TEN = [SESSION_IDS[index - 1] for index in range(12, 2, -1)]


@dataclass(frozen=True, slots=True)
class LatestTenEnvironment:
    """Seeded two-workspace corpus plus authenticated workspace readers."""

    client: httpx.AsyncClient
    database: Database
    admin: dict[str, str]
    alice: dict[str, str]
    bob: dict[str, str]
    workspace_a: str
    workspace_b: str


def extra_started_at(index: int) -> datetime:
    """Place the synthetic additions after every seeded session."""
    return datetime(2026, 11, 1, 9, 0, tzinfo=SHANGHAI) + timedelta(days=index - 5)


def extra_session_values(
    base: dict[str, Any],
    *,
    index: int,
    status: str,
) -> dict[str, Any]:
    """Copy one canonical aggregate row into a deterministic synthetic root."""
    started_at = extra_started_at(index)
    return {
        **base,
        "id": SESSION_IDS[index - 1],
        "short_title": f"最新会话 {index:02d}",
        "title": f"最新会话 {index:02d} 批量投影",
        "search_text": f"最新会话 {index:02d} 批量投影 example-repo",
        "repo_name": "example-repo",
        "started_at": started_at,
        "ended_at": started_at + timedelta(minutes=1),
        "duration_seconds": 60,
        "status": status,
        "models": ["claude-sonnet-synthetic"],
        "skill_names": [],
        "user_turns_count": 1,
        "messages_count": 1,
        "tools_count": 0,
        "errors_count": 0,
        "agents_count": 0,
        "tokens_total": 40,
        "source_type": "script",
        "imported_at": started_at,
        "updated_at": started_at,
    }


def bad_case_values(
    *,
    bad_case_id: str,
    workspace_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Build one externally owned case projecting a root into a workspace."""
    now = now_shanghai()
    return {
        "bad_case_id": bad_case_id,
        "workspace_id": workspace_id,
        "bad_case_session_id": session_id,
        "bad_case_type": "self",
        "object_name": "latest-ten",
        "object_type": "skill",
        "object_version": "v1",
        "bad_case_agent_id": None,
        "title": f"Case {bad_case_id}",
        "bad_case_description": "Projects one synthetic root for latest-ten tests.",
        "meta_data": None,
        "source": "tests",
        "created_at": now,
        "updated_at": now,
    }
