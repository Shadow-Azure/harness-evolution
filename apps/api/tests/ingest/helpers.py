"""Workspace, credential, and payload helpers for the ingest tests."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import func, select

from app.db.base import Database
from app.db.models.domain import bad_cases, workspace_bad_cases
from app.utils.time import as_shanghai
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
    insert_workspace,
)

SESSION_ID = "11111111-1111-4111-8111-111111111111"
CREATED_AT = "2026-11-09T15:58:00+08:00"


@dataclass(frozen=True, slots=True)
class IngestWorkspace:
    """One seeded workspace with its space-admin token and ingest credential."""

    workspace_id: str
    credential: str
    admin_token: str

    @property
    def authorization(self) -> dict[str, str]:
        """Return the workspace credential header used by the ingest route."""
        return bearer(self.credential)

    @property
    def admin_authorization(self) -> dict[str, str]:
        """Return the space-admin access token header used by admin routes."""
        return bearer(self.admin_token)


def ingest_body(**overrides: Any) -> dict[str, Any]:
    """Return one valid camelCase ingest payload with targeted overrides."""
    body: dict[str, Any] = {
        "badCaseId": "BC-HC-021",
        "sessionId": SESSION_ID,
        "badCaseType": "self",
        "objectName": "deep-research",
        "objectType": "skill",
        "objectVersion": "v2.4.0",
        "badCaseAgentId": None,
        "title": "输出缺少来源校验",
        "reason": "12 条结论中有 5 条没有附带来源。",
        "metaData": {"file": "skills/deep-research/SKILL.md", "line": 91},
        "source": "agent-runtime",
        "createdAt": CREATED_AT,
    }
    body.update(overrides)
    return body


async def create_ingest_workspace(
    app: FastAPI,
    client: httpx.AsyncClient,
    *,
    name: str,
    quota: int = 10,
    username: str | None = None,
) -> IngestWorkspace:
    """Seed one workspace with a space admin and mint a real ingest credential."""
    database = app.state.database
    workspace_id = await insert_workspace(database, name=name, quota=quota)
    user_id = await create_user(database, username=username or f"admin-{name.lower()}")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=user_id,
        role="space_admin",
    )
    admin_token = access_token(app, user_id=user_id)
    created = await client.post(
        f"/api/workspaces/{workspace_id}/credentials",
        headers=bearer(admin_token),
    )
    if created.status_code != 201:
        raise RuntimeError(f"credential creation failed: {created.text}")
    credential: str = created.json()["credential"]
    return IngestWorkspace(
        workspace_id=workspace_id,
        credential=credential,
        admin_token=admin_token,
    )


async def report(
    client: httpx.AsyncClient,
    workspace: IngestWorkspace,
    body: dict[str, Any],
    *,
    workspace_id: str | None = None,
) -> httpx.Response:
    """Post one ingest payload for the workspace, optionally to another path id."""
    return await client.post(
        f"/api/workspaces/{workspace_id or workspace.workspace_id}/bad-cases",
        headers=workspace.authorization,
        json=body,
    )


async def count_cases(database: Database, workspace_id: str) -> int:
    """Return the live bad-case count for one workspace."""
    async with database.session() as session:
        return int(
            (
                await session.execute(
                    select(func.count(func.distinct(workspace_bad_cases.c.bad_case_id))).where(
                        workspace_bad_cases.c.workspace_id == workspace_id,
                    ),
                )
            ).scalar_one(),
        )


async def fetch_case(database: Database, bad_case_id: str) -> dict[str, Any] | None:
    """Return one stored bad-case row as a mapping."""
    async with database.session() as session:
        row = (
            (
                await session.execute(
                    select(bad_cases).where(bad_cases.c.bad_case_id == bad_case_id),
                )
            )
            .mappings()
            .one_or_none()
        )
    return dict(row) if row is not None else None


def stored_created_at(row: dict[str, Any]) -> datetime:
    """Normalize a stored timestamp back to Asia/Shanghai for assertions."""
    value = row["created_at"]
    assert isinstance(value, datetime)
    return as_shanghai(value)
