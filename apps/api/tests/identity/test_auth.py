"""End-to-end authentication and password lifecycle behavior."""

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import jwt
import pytest
from sqlalchemy import update as sqlalchemy_update

from app.db.models.users import users
from app.errors import ErrorCode
from app.main import create_app
from app.middleware.rate_limit import LoginRateLimiter
from tests.identity.helpers import change_admin_password, identity_settings, login


async def test_seeded_admin_can_login_and_change_forced_password(tmp_path: Path) -> None:
    """Initial credentials work once, force a password change, and clear the flag."""
    settings = identity_settings(
        tmp_path,
        admin_username="Admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        response = await login(client)

        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == {"accessToken", "expiresIn", "user"}
        assert payload["expiresIn"] == 1_800
        assert payload["user"] == {
            "id": payload["user"]["id"],
            "username": "admin",
            "displayName": "Administrator",
            "role": "admin",
            "mustChangePassword": True,
        }
        refresh_cookie = response.cookies.get("refresh_token")
        assert refresh_cookie
        set_cookie = response.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie
        assert "Path=/api/auth" in set_cookie
        assert "Max-Age=1209600" in set_cookie
        assert "Secure" not in set_cookie

        me = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {payload['accessToken']}"},
        )
        assert me.status_code == 200
        assert me.json()["mustChangePassword"] is True

        forbidden = await client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {payload['accessToken']}"},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

        wrong_old_password = await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {payload['accessToken']}"},
            json={"oldPassword": "wrong-password", "newPassword": "replacement-password"},
        )
        assert wrong_old_password.status_code == 401
        assert wrong_old_password.json()["error"]["code"] == "AUTH_INVALID"

        changed = await change_admin_password(client)
        assert changed.status_code == 204

        refreshed = await client.post("/api/auth/refresh")
        assert refreshed.status_code == 200
        assert set(refreshed.json()) == {"accessToken", "expiresIn"}


async def test_login_updates_last_login_and_refresh_does_not(tmp_path: Path) -> None:
    """Only successful password login records the authentication timestamp."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        authenticated = await login(client)
        after_login = await app.state.identity.users.get_by_username("admin")
        assert after_login is not None
        last_login = after_login.last_login_at
        assert last_login is not None
        assert last_login.utcoffset() == timedelta(hours=8)

        refreshed = await client.post("/api/auth/refresh")
        after_refresh = await app.state.identity.users.get_by_username("admin")

    assert authenticated.status_code == 200
    assert refreshed.status_code == 200
    assert after_refresh is not None
    assert after_refresh.last_login_at == last_login


async def test_wrong_password_returns_the_same_invalid_identity_error(tmp_path: Path) -> None:
    """Authentication does not reveal whether a username exists."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        wrong_password = await login(client, password="wrong-password")
        unknown_user = await login(client, username="missing", password="wrong-password")

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json()["error"]["code"] == "AUTH_INVALID"
    assert unknown_user.json()["error"]["code"] == "AUTH_INVALID"
    assert wrong_password.json() == unknown_user.json()


async def test_expired_access_token_requires_refresh(tmp_path: Path) -> None:
    """Expired bearer tokens map to the dedicated refreshable error code."""
    from app.service.identity.tokens import TokenService

    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    expired = TokenService(settings).create_access_token(
        user_id="user-1",
        role="member",
        must_change_password=False,
        expires_in=-1,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/users", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_EXPIRED"


async def test_malformed_and_mistyped_credentials_fail_closed(tmp_path: Path) -> None:
    """Malformed bearer credentials stay distinct from expired access tokens."""
    from app.service.identity.tokens import TokenService

    settings = identity_settings(tmp_path)
    app = create_app(settings)
    refresh_token = TokenService(settings).create_refresh_token(user_id="user-1")
    malformed_claims = jwt.encode(
        {"typ": "access"},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing = await client.get("/api/users")
        wrong_scheme = await client.get(
            "/api/users",
            headers={"Authorization": "Basic api-test-signing-secret"},
        )
        malformed = await client.get(
            "/api/users",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        refresh_as_access = await client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        malformed_claims_response = await client.get(
            "/api/users",
            headers={"Authorization": f"Bearer {malformed_claims}"},
        )
        client.cookies.set("refresh_token", "not-a-jwt", domain="testserver", path="/api/auth")
        malformed_refresh = await client.post("/api/auth/refresh")

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == ErrorCode.AUTH_REQUIRED
    assert wrong_scheme.status_code == 401
    assert wrong_scheme.json()["error"]["code"] == ErrorCode.AUTH_REQUIRED
    assert malformed.status_code == 401
    assert malformed.json()["error"]["code"] == ErrorCode.AUTH_REQUIRED
    assert refresh_as_access.status_code == 401
    assert refresh_as_access.json()["error"]["code"] == ErrorCode.AUTH_REQUIRED
    assert malformed_claims_response.status_code == 401
    assert malformed_claims_response.json()["error"]["code"] == ErrorCode.AUTH_REQUIRED
    assert malformed_refresh.status_code == 401
    assert malformed_refresh.json()["error"]["code"] == ErrorCode.AUTH_EXPIRED


async def test_inactive_users_cannot_login_or_refresh(tmp_path: Path) -> None:
    """Disabling an account blocks both initial login and cookie rotation."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        admin = await login(client)
        await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {admin.json()['accessToken']}"},
            json={"oldPassword": "initial-password", "newPassword": "replacement-password"},
        )
        refreshed_admin = await client.post("/api/auth/refresh")
        await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {refreshed_admin.json()['accessToken']}"},
            json={
                "username": "member",
                "displayName": "Member",
                "password": "temporary-password",
                "role": "member",
            },
        )
        member = await login(client, username="member", password="temporary-password")
        member_record = await app.state.identity.users.get_by_username("member")
        assert member_record is not None
        async with app.state.database.transaction() as session:
            await session.execute(
                sqlalchemy_update(users)
                .where(users.c.id == member_record.id)
                .values(is_active=False)
            )

        disabled_login = await login(
            client,
            username="member",
            password="temporary-password",
        )
        disabled_refresh = await client.post("/api/auth/refresh")

    assert member.status_code == 200
    assert disabled_login.status_code == 403
    assert disabled_login.json()["error"]["code"] == ErrorCode.FORBIDDEN
    assert disabled_refresh.status_code == 403
    assert disabled_refresh.json()["error"]["code"] == ErrorCode.FORBIDDEN


async def test_refresh_rotation_rejects_the_previous_token(tmp_path: Path) -> None:
    """Each refresh rotates the cookie and one-time invalidates the old refresh token."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        first = await login(client)
        assert first.status_code == 200
        first_refresh = first.cookies.get("refresh_token")
        assert first_refresh

        second = await client.post("/api/auth/refresh")
        assert second.status_code == 200
        second_refresh = second.cookies.get("refresh_token")
        assert second_refresh
        assert second_refresh != first_refresh

        client.cookies.clear()
        client.cookies.set("refresh_token", first_refresh, domain="testserver", path="/api/auth")
        replay = await client.post("/api/auth/refresh")
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "AUTH_EXPIRED"


async def test_concurrent_refresh_consumes_each_token_only_once(tmp_path: Path) -> None:
    """A racing replay receives one new pair while the other request is rejected."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        authenticated = await login(client)
        refresh_token = authenticated.cookies.get("refresh_token")
        assert refresh_token
        headers = {"Cookie": f"refresh_token={refresh_token}"}

        responses = await asyncio.gather(
            client.post("/api/auth/refresh", headers=headers),
            client.post("/api/auth/refresh", headers=headers),
        )

    assert sorted(response.status_code for response in responses) == [200, 401]
    rejected = next(response for response in responses if response.status_code == 401)
    assert rejected.json()["error"]["code"] == ErrorCode.AUTH_EXPIRED


async def test_expired_refresh_token_is_rejected(tmp_path: Path) -> None:
    """Refresh tokens use the dedicated expired credential error after their TTL."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        authenticated = await login(client)
        user_id = authenticated.json()["user"]["id"]
        expired = jwt.encode(
            {
                "sub": user_id,
                "typ": "refresh",
                "jti": "expired-refresh",
                "exp": 1,
            },
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        client.cookies.clear()
        client.cookies.set("refresh_token", expired, domain="testserver", path="/api/auth")
        response = await client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == ErrorCode.AUTH_EXPIRED


async def test_production_refresh_cookie_is_secure(tmp_path: Path) -> None:
    """Production cookies require HTTPS transport in addition to HTTP-only scoping."""
    settings = identity_settings(
        tmp_path,
        production=True,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="https://testserver") as client,
    ):
        response = await login(client)

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


async def test_empty_seeded_admin_password_does_not_create_an_account(tmp_path: Path) -> None:
    """An empty deployment secret is treated as missing rather than hashed literally."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        users_count = await app.state.identity.users.count()

    assert users_count == 0


async def test_login_is_limited_to_ten_attempts_per_ip_per_minute(tmp_path: Path) -> None:
    """Request validation does not bypass the per-IP brute-force boundary."""
    settings = identity_settings(tmp_path)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        responses = [await client.post("/api/auth/login", json={}) for _ in range(11)]

    assert [response.status_code for response in responses[:10]] == [422] * 10
    assert responses[10].status_code == 429
    assert responses[10].json()["error"]["code"] == ErrorCode.RATE_LIMITED
    assert responses[10].headers["Retry-After"] == "60"


async def test_login_limit_window_resets(tmp_path: Path) -> None:
    """A blocked IP can authenticate again after its oldest attempts leave the window."""
    now = [100.0]
    app = create_app(identity_settings(tmp_path))
    app.state.login_rate_limiter = LoginRateLimiter(
        limit=1,
        window_seconds=60,
        clock=lambda: now[0],
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        first = await client.post("/api/auth/login", json={})
        blocked = await client.post("/api/auth/login", json={})
        now[0] = 161.0
        allowed_again = await client.post("/api/auth/login", json={})

    assert first.status_code == 422
    assert blocked.status_code == 429
    assert allowed_again.status_code == 422


async def test_member_role_cannot_use_admin_user_directory(tmp_path: Path) -> None:
    """The middleware enforces the admin boundary for user administration."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        admin = await login(client)
        await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {admin.json()['accessToken']}"},
            json={"oldPassword": "initial-password", "newPassword": "replacement-password"},
        )
        await client.post("/api/auth/refresh")
        replacement = await login(client, password="replacement-password")
        await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {replacement.json()['accessToken']}"},
            json={
                "username": "member",
                "displayName": "Member",
                "password": "temporary-password",
                "role": "member",
            },
        )
        member = await login(client, username="member", password="temporary-password")
        member_access = member.json()["accessToken"]
        changed = await client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {member_access}"},
            json={"oldPassword": "temporary-password", "newPassword": "member-password"},
        )
        refreshed = await client.post("/api/auth/refresh")
        refreshed_access = refreshed.json()["accessToken"]
        headers = {"Authorization": f"Bearer {refreshed_access}"}

        listed = await client.get("/api/users", headers=headers)
        missing_admin_path = await client.get("/api/users/missing", headers=headers)
        created = await client.post(
            "/api/users",
            headers=headers,
            json={
                "username": "unauthorized",
                "displayName": "Unauthorized",
                "password": "temporary-password",
                "role": "member",
            },
        )

    assert changed.status_code == 204
    assert refreshed.status_code == 200
    assert listed.status_code == 403
    assert listed.json()["error"]["code"] == "FORBIDDEN"
    assert missing_admin_path.status_code == 403
    assert missing_admin_path.json()["error"]["code"] == "FORBIDDEN"
    assert created.status_code == 403
    assert created.json()["error"]["code"] == "FORBIDDEN"


async def test_logout_revokes_the_current_refresh_token(tmp_path: Path) -> None:
    """Logout clears the cookie and prevents reuse of its refresh token."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        authenticated = await login(client)
        access = authenticated.json()["accessToken"]
        refresh = authenticated.cookies.get("refresh_token")
        assert refresh

        logout = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access}"},
        )
        assert logout.status_code == 204
        assert logout.headers["set-cookie"].startswith('refresh_token=""')

        client.cookies.clear()
        client.cookies.set("refresh_token", refresh, domain="testserver", path="/api/auth")
        replay = await client.post("/api/auth/refresh")
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "AUTH_EXPIRED"


@pytest.mark.usefixtures("identity_client")
async def test_business_api_requires_a_bearer_token(identity_client: httpx.AsyncClient) -> None:
    """The default API surface remains fail-closed after identity routes exist."""
    response = await identity_client.get("/api/users")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"
