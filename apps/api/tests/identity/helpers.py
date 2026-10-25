"""Test helpers for identity application flows."""

from pathlib import Path

import httpx

from app.config import DatabaseDialect, Settings


def identity_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Build an isolated identity service configuration."""
    values: dict[str, object] = {
        "db_dialect": DatabaseDialect.SQLITE,
        "data_dir": tmp_path,
        "jwt_secret": "identity-test-signing-secret-with-sufficient-length",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def login(
    client: httpx.AsyncClient,
    *,
    username: str = "admin",
    password: str = "initial-password",
) -> httpx.Response:
    """Authenticate through the public login endpoint."""
    return await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


async def change_admin_password(client: httpx.AsyncClient) -> httpx.Response:
    """Move the seeded administrator out of forced-password-change state."""
    response = await login(client)
    return await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {response.json()['accessToken']}"},
        json={"oldPassword": "initial-password", "newPassword": "replacement-password"},
    )
