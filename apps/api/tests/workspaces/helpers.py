"""Fixtures and seeding helpers for workspace RBAC and session tests."""

from datetime import datetime, timedelta
from typing import Annotated, cast

from fastapi import Depends, FastAPI
from sqlalchemy import insert

from app.api.deps import require_workspace_role
from app.db.base import Database
from app.db.crud.fixtures import (
    backfill_legacy_associations as fixtures_backfill_legacy_associations,
)
from app.db.models.domain import bad_cases, workspace_bad_cases
from app.db.models.users import users
from app.db.models.workspace import workspace_members, workspaces
from app.service.workspaces.service import WorkspaceAccess
from app.utils.ids import new_id
from app.utils.time import now_shanghai


async def create_user(
    database: Database,
    *,
    username: str,
    role: str = "member",
    must_change_password: bool = False,
) -> str:
    """Insert one user row without exercising the password flow."""
    user_id = new_id()
    now = now_shanghai()
    placeholder_hash = "not-used-by-workspace-tests"
    async with database.transaction() as session:
        await session.execute(
            insert(users).values(
                id=user_id,
                username=username,
                password_hash=placeholder_hash,
                display_name=username,
                role=role,
                is_active=True,
                must_change_password=must_change_password,
                created_at=now,
                updated_at=now,
            ),
        )
    return user_id


async def insert_workspace(
    database: Database,
    *,
    name: str,
    quota: int = 10,
    created_at: datetime | None = None,
) -> str:
    """Insert one active workspace row and return its stable id."""
    workspace_id = new_id()
    now = created_at or now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            insert(workspaces).values(
                id=workspace_id,
                name=name,
                mark=name,
                quota=quota,
                status="active",
                created_at=now,
                updated_at=now,
            ),
        )
    return workspace_id


async def insert_member(
    database: Database,
    *,
    workspace_id: str,
    user_id: str,
    role: str,
) -> None:
    """Insert one membership row for the given workspace and user."""
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            insert(workspace_members).values(
                workspace_id=workspace_id,
                user_id=user_id,
                role=role,
                joined_at=now,
                updated_at=now,
            ),
        )


async def insert_bad_case(
    database: Database,
    *,
    workspace_id: str,
    bad_case_id: str,
) -> None:
    """Insert one minimally valid bad case owned by the workspace."""
    now = now_shanghai()
    async with database.transaction() as session:
        await session.execute(
            insert(bad_cases).values(
                bad_case_id=bad_case_id,
                workspace_id=workspace_id,
                bad_case_session_id=f"session-{bad_case_id}",
                bad_case_type="self",
                object_name="example-object",
                object_type="skill",
                title=f"Case {bad_case_id}",
                bad_case_description="Seeded only for workspace aggregate tests.",
                created_at=now,
                updated_at=now,
            ),
        )
        await session.execute(
            insert(workspace_bad_cases).values(
                workspace_id=workspace_id,
                bad_case_id=bad_case_id,
                assignment_source="legacy_owner",
                label=None,
                assigned_at=now,
            ),
        )


async def associate_case(
    database: Database,
    *,
    workspace_id: str,
    bad_case_id: str,
    source: str = "legacy_owner",
    label: str | None = None,
) -> None:
    """Insert one workspace→bad-case association for scoped read tests."""
    async with database.transaction() as session:
        await session.execute(
            insert(workspace_bad_cases).values(
                workspace_id=workspace_id,
                bad_case_id=bad_case_id,
                assignment_source=source,
                label=label,
                assigned_at=now_shanghai(),
            ),
        )


async def backfill_legacy_associations(database: Database) -> None:
    """Mirror migration 0034 for fixtures that seed ownership without associations.

    Delegates to the shared corpus/fixture helper so the migration semantics
    live in one place; the ``NOT EXISTS`` guard keeps repeated calls idempotent.
    """
    await fixtures_backfill_legacy_associations(database)


def access_token(
    app: FastAPI,
    *,
    user_id: str,
    role: str = "member",
    must_change_password: bool = False,
) -> str:
    """Mint a valid bearer token for a seeded user without a password round trip."""
    token: str = cast(
        str,
        app.state.identity.tokens.create_access_token(
            user_id=user_id,
            role=role,
            must_change_password=must_change_password,
        ),
    )
    return token


def bearer(token: str) -> dict[str, str]:
    """Return the authorization header for one bearer token."""
    return {"Authorization": f"Bearer {token}"}


def mount_role_probes(app: FastAPI) -> None:
    """Expose the real dependency through one probe route per minimum role."""

    async def viewer_probe(
        access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    ) -> dict[str, str]:
        return {"role": access.role}

    async def member_probe(
        access: Annotated[WorkspaceAccess, Depends(require_workspace_role("member"))],
    ) -> dict[str, str]:
        return {"role": access.role}

    async def space_admin_probe(
        access: Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))],
    ) -> dict[str, str]:
        return {"role": access.role}

    app.add_api_route("/api/test/workspaces/{wid}/viewer", viewer_probe, methods=["GET"])
    app.add_api_route("/api/test/workspaces/{wid}/member", member_probe, methods=["GET"])
    app.add_api_route(
        "/api/test/workspaces/{wid}/space-admin",
        space_admin_probe,
        methods=["GET"],
    )


async def insert_workspaces_for_user(
    database: Database,
    *,
    user_id: str,
    count: int,
) -> list[str]:
    """Create ``count`` workspaces where the user is a viewer, oldest first."""
    start = now_shanghai() - timedelta(minutes=count)
    workspace_ids: list[str] = []
    for index in range(count):
        workspace_id = await insert_workspace(
            database,
            name=f"bulk-workspace-{index:03d}",
            created_at=start + timedelta(minutes=index),
        )
        await insert_member(
            database,
            workspace_id=workspace_id,
            user_id=user_id,
            role="viewer",
        )
        workspace_ids.append(workspace_id)
    return workspace_ids
