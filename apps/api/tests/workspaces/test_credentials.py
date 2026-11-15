"""Ingest credential creation, rotation, revocation, and authentication contracts."""

import hashlib

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.db.models.workspace import workspace_ingest_credentials
from app.errors import AppError
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
    insert_workspace,
)


async def _admin(app: FastAPI) -> tuple[str, dict[str, str]]:
    """Create the global administrator and return its id and bearer header."""
    admin_id = await create_user(app.state.database, username="cred-root", role="admin")
    return admin_id, bearer(access_token(app, user_id=admin_id, role="admin"))


async def _space_admin(
    app: FastAPI,
    workspace_id: str,
    username: str = "cred-admin",
) -> tuple[str, dict[str, str]]:
    """Create one workspace administrator and return its id and bearer header."""
    user_id = await create_user(app.state.database, username=username)
    await insert_member(
        app.state.database,
        workspace_id=workspace_id,
        user_id=user_id,
        role="space_admin",
    )
    return user_id, bearer(access_token(app, user_id=user_id))


async def test_create_credential_returns_plaintext_once_and_stores_only_hash(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The one-time secret never appears in the database or a later list response."""
    app, client = workspace_client
    database = app.state.database
    workspace_id = await insert_workspace(database, name="Ingest")
    _, header = await _space_admin(app, workspace_id)

    created = await client.post(
        f"/api/workspaces/{workspace_id}/credentials",
        headers=header,
    )

    assert created.status_code == 201
    payload = created.json()
    assert set(payload) == {"credentialId", "prefix", "credential"}
    assert payload["credential"].startswith("whk_")
    assert payload["prefix"] == payload["credential"][:12]
    assert len(payload["prefix"]) == 12

    async with database.session() as session:
        row = (
            (
                await session.execute(
                    select(workspace_ingest_credentials).where(
                        workspace_ingest_credentials.c.id == payload["credentialId"],
                    ),
                )
            )
            .mappings()
            .one()
        )
    assert (
        row["credential_hash"]
        == hashlib.sha256(
            payload["credential"].encode(),
        ).hexdigest()
    )
    assert row["credential_prefix"] == payload["prefix"]
    assert row["revoked_at"] is None
    assert payload["credential"] not in {row["credential_hash"], row["credential_prefix"]}

    listed = await client.get(
        f"/api/workspaces/{workspace_id}/credentials",
        headers=header,
    )
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert set(item) == {"id", "prefix", "createdAt", "lastUsedAt", "revokedAt"}
    assert item["id"] == payload["credentialId"]
    assert item["prefix"] == payload["prefix"]
    assert item["lastUsedAt"] is None
    assert item["revokedAt"] is None
    assert "credential" not in item


async def test_revoked_credential_cannot_authenticate_but_stays_visible(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Revocation keeps the audit row and makes the plaintext unusable immediately."""
    app, client = workspace_client
    database = app.state.database
    workspace_id = await insert_workspace(database, name="Rotate")
    _, header = await _space_admin(app, workspace_id)
    created = (
        await client.post(
            f"/api/workspaces/{workspace_id}/credentials",
            headers=header,
        )
    ).json()

    authenticated = await app.state.workspaces.verify_credential(created["credential"])
    revoked = await client.delete(
        f"/api/workspaces/{workspace_id}/credentials/{created['credentialId']}",
        headers=header,
    )
    with pytest.raises(AppError) as rejection:
        await app.state.workspaces.verify_credential(created["credential"])

    assert authenticated.workspace_id == workspace_id
    assert authenticated.credential_id == created["credentialId"]
    assert revoked.status_code == 204
    assert rejection.value.code == "CREDENTIAL_INVALID"
    assert rejection.value.status_code == 401

    listed = await client.get(
        f"/api/workspaces/{workspace_id}/credentials",
        headers=header,
    )
    item = listed.json()["items"][0]
    assert item["revokedAt"] is not None

    again = await client.delete(
        f"/api/workspaces/{workspace_id}/credentials/{created['credentialId']}",
        headers=header,
    )
    assert again.status_code == 204


async def test_unknown_credential_or_token_is_not_accepted(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Unknown credential ids and hashes both fail closed."""
    app, client = workspace_client
    database = app.state.database
    workspace_id = await insert_workspace(database, name="UnknownCred")
    _, header = await _space_admin(app, workspace_id)

    missing = await client.delete(
        f"/api/workspaces/{workspace_id}/credentials/cred-missing",
        headers=header,
    )
    with pytest.raises(AppError) as rejection:
        await app.state.workspaces.verify_credential("whk_missing-token")
    with pytest.raises(AppError) as unnamespaced:
        await app.state.workspaces.verify_credential("not-a-workspace-token")
    with pytest.raises(AppError) as missing_header:
        await app.state.workspaces.verify_credential(None)

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CREDENTIAL_NOT_FOUND"
    assert rejection.value.code == "CREDENTIAL_INVALID"
    assert unnamespaced.value.code == "CREDENTIAL_INVALID"
    assert missing_header.value.code == "CREDENTIAL_INVALID"


async def test_credentials_are_capped_at_three_active_rows(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A fourth active credential is refused; revoking one frees a slot."""
    app, client = workspace_client
    database = app.state.database
    workspace_id = await insert_workspace(database, name="LimitCred")
    _, header = await _space_admin(app, workspace_id)

    created = [
        await client.post(
            f"/api/workspaces/{workspace_id}/credentials",
            headers=header,
        )
        for _ in range(3)
    ]
    refused = await client.post(
        f"/api/workspaces/{workspace_id}/credentials",
        headers=header,
    )
    first = created[0].json()
    await client.delete(
        f"/api/workspaces/{workspace_id}/credentials/{first['credentialId']}",
        headers=header,
    )
    replacement = await client.post(
        f"/api/workspaces/{workspace_id}/credentials",
        headers=header,
    )

    assert [response.status_code for response in created] == [201, 201, 201]
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "CREDENTIAL_LIMIT"
    assert replacement.status_code == 201


async def test_credential_management_requires_space_admin_and_matching_workspace(
    workspace_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """Members read nothing here; cross-workspace ids stay invisible."""
    app, client = workspace_client
    database = app.state.database
    workspace_id = await insert_workspace(database, name="CredScope")
    other_id = await insert_workspace(database, name="CredOther")
    member_id = await create_user(database, username="cred-member")
    await insert_member(
        database,
        workspace_id=workspace_id,
        user_id=member_id,
        role="member",
    )
    member_header = bearer(access_token(app, user_id=member_id))
    _, admin_header = await _admin(app)
    created = (
        await client.post(
            f"/api/workspaces/{workspace_id}/credentials",
            headers=admin_header,
        )
    ).json()

    listed = await client.get(
        f"/api/workspaces/{workspace_id}/credentials",
        headers=member_header,
    )
    created_by_member = await client.post(
        f"/api/workspaces/{workspace_id}/credentials",
        headers=member_header,
    )
    wrong_space = await client.delete(
        f"/api/workspaces/{other_id}/credentials/{created['credentialId']}",
        headers=admin_header,
    )

    assert listed.status_code == 403
    assert listed.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert created_by_member.status_code == 403
    assert wrong_space.status_code == 404
    assert wrong_space.json()["error"]["code"] == "CREDENTIAL_NOT_FOUND"
