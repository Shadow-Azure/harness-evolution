"""Auth-provider seam, callback failure codes, and the single-admin boundary."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import update

from app.config import AuthProviderName, Settings
from app.db.models.users import users
from app.errors import ErrorCode
from app.main import create_app
from app.service.identity.callback import (
    CALLBACK_STATE_COOKIE,
    CallbackService,
    CallbackStateStore,
)
from app.service.identity.providers import (
    AuthProviderConfigurationError,
    AuthProviderError,
    Credentials,
    ProviderIdentity,
    ProviderRegistry,
)
from app.service.identity.session_bridge import SessionBridge
from tests.identity.helpers import change_admin_password, identity_settings, login


class StubExternalProvider:
    """Deterministic external provider used to exercise the callback branches."""

    name = AuthProviderName.OIDC

    def __init__(
        self,
        identity: ProviderIdentity | None = None,
        error: AuthProviderError | None = None,
    ) -> None:
        """Configure the provider outcome and record its inputs."""
        self.identity = identity
        self.error = error
        self.credentials: Credentials | None = None
        self.calls = 0

    async def authenticate(self, credentials: Credentials) -> ProviderIdentity | None:
        """Return the configured outcome while recording the credential payload."""
        self.calls += 1
        self.credentials = credentials
        if self.error is not None:
            raise self.error
        return self.identity


def install_callback(
    app: FastAPI,
    settings: Settings,
    provider: StubExternalProvider,
    *,
    state_store: CallbackStateStore | None = None,
) -> CallbackService:
    """Replace the application callback with a deterministic external provider."""
    identity = app.state.identity
    registry = ProviderRegistry(
        password=identity.providers.password,
        external=provider,
    )
    callback = CallbackService(
        settings,
        registry,
        identity.bridge,
        state_store=state_store,
    )
    identity.callback = callback
    return callback


def set_state_cookie(client: httpx.AsyncClient, callback: CallbackService) -> str:
    """Write the challenge a future start endpoint would put in the cookie."""
    challenge = callback.state_challenge()
    client.cookies.set(
        CALLBACK_STATE_COOKIE,
        challenge.value,
        path="/api/auth",
    )
    return challenge.value


async def map_user(
    app: FastAPI,
    username: str,
    *,
    provider: str = "oidc",
    subject: str = "subject-1",
    is_active: bool = True,
) -> None:
    """Point one existing user row at an external identity without creating rows."""
    record = await app.state.identity.users.get_by_username(username)
    assert record is not None
    async with app.state.database.transaction() as session:
        await session.execute(
            update(users)
            .where(users.c.id == record.id)
            .values(
                auth_provider=provider,
                external_subject=subject,
                is_active=is_active,
            ),
        )


async def test_default_settings_keep_the_password_provider(tmp_path: Path) -> None:
    """Defaults select password and expose the cookie/OIDC knobs as reserved."""
    settings = identity_settings(tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        identity = app.state.identity
        assert settings.auth_provider is AuthProviderName.PASSWORD
        assert settings.session_cookie_name == "he_session"
        assert settings.session_ttl_hours == 12
        assert settings.oidc_configured is False
        assert identity.providers.password.name is AuthProviderName.PASSWORD
        assert identity.providers.external is None
        assert identity.callback.configured is False


@pytest.mark.parametrize("provider", [AuthProviderName.COOKIE, AuthProviderName.OIDC])
async def test_reserved_providers_fail_startup(
    tmp_path: Path,
    provider: AuthProviderName,
) -> None:
    """Selecting an unimplemented provider fails before the server can accept requests."""
    settings = identity_settings(tmp_path, auth_provider=provider)
    with pytest.raises(AuthProviderConfigurationError, match="reserved and not implemented"):
        create_app(settings)


async def test_invalid_provider_names_are_rejected(tmp_path: Path) -> None:
    """An unknown HE_AUTH_PROVIDER value cannot silently fall back to password."""
    with pytest.raises(ValidationError):
        identity_settings(tmp_path, auth_provider="saml")


async def test_password_login_still_enters_through_the_provider(tmp_path: Path) -> None:
    """The existing login contract is preserved after moving verification into a provider."""
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
        accepted = await login(client)
        rejected = await login(client, password="wrong-password")

    assert accepted.status_code == 200
    assert accepted.json()["user"]["username"] == "admin"
    assert accepted.cookies.get("refresh_token")
    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == ErrorCode.AUTH_INVALID


async def test_provider_registry_requires_a_password_provider() -> None:
    """A registry without the password provider cannot serve the default flow."""
    with pytest.raises(AuthProviderConfigurationError, match="password provider"):
        _ = ProviderRegistry().password


async def test_session_bridge_rejects_missing_internal_and_external_users(
    tmp_path: Path,
) -> None:
    """Mapping never creates a user and distinguishes password loss from no mapping."""
    settings = identity_settings(tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        bridge: SessionBridge = app.state.identity.bridge
        with pytest.raises(Exception) as missing_password:
            await bridge.resolve(ProviderIdentity(AuthProviderName.PASSWORD, "missing"))
        with pytest.raises(Exception) as missing_external:
            await bridge.resolve(ProviderIdentity(AuthProviderName.OIDC, "missing"))
        empty_subject = await app.state.identity.users.get_by_provider_subject(
            provider="oidc",
            subject="",
        )

    assert getattr(missing_password.value, "code", None) == ErrorCode.AUTH_INVALID
    assert getattr(missing_external.value, "code", None) == ErrorCode.AUTH_NO_MAPPING
    assert empty_subject is None


async def test_callback_without_a_provider_returns_501_and_creates_no_user(
    tmp_path: Path,
) -> None:
    """The placeholder callback fails closed before any state or mapping work."""
    settings = identity_settings(tmp_path)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        response = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": "state-1"},
        )
        users_after = await app.state.identity.users.count()

    assert response.status_code == 501
    assert response.json()["error"]["code"] == ErrorCode.AUTH_PROVIDER_NOT_CONFIGURED
    assert users_after == 0


async def test_state_challenge_describes_the_cookie_writer(tmp_path: Path) -> None:
    """The challenge carries the cookie name, lifetime, and transport flags."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        challenge = app.state.identity.callback.state_challenge()
        production_settings = identity_settings(
            tmp_path,
            production=True,
            admin_username="admin",
            admin_password="initial-password",
        )
        production = create_app(production_settings)
        async with production.router.lifespan_context(production):
            secure_challenge = production.state.identity.callback.state_challenge()

    assert challenge.cookie_name == CALLBACK_STATE_COOKIE
    assert challenge.max_age == 600
    assert challenge.samesite == "lax"
    assert challenge.secure is False
    assert secure_challenge.secure is True


async def test_callback_success_issues_the_same_session_pair(tmp_path: Path) -> None:
    """A mapped external identity receives the password-login token pair and a redirect."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
        web_base_url="https://harness.example",
    )
    app = create_app(settings)
    provider = StubExternalProvider(
        ProviderIdentity(AuthProviderName.OIDC, "subject-1", "admin@example.com"),
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        await map_user(app, "admin")
        callback = install_callback(app, settings, provider)
        state = set_state_cookie(client, callback)
        response = await client.get(
            "/api/auth/callback",
            params={"code": "authorization-code", "state": state},
        )
        user = await app.state.identity.users.get_by_username("admin")
        users_after = await app.state.identity.users.count()

    assert response.status_code == 302
    assert response.headers["location"] == "https://harness.example"
    assert response.cookies.get("refresh_token")
    assert CALLBACK_STATE_COOKIE not in response.cookies
    assert provider.calls == 1
    assert provider.credentials == Credentials(code="authorization-code")
    assert user is not None and user.last_login_at is not None
    assert users_after == 1


async def test_callback_rejects_missing_mismatched_forged_and_expired_state(
    tmp_path: Path,
) -> None:
    """Every state failure maps to one stable 400 without reaching the provider."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    provider = StubExternalProvider(ProviderIdentity(AuthProviderName.OIDC, "subject-1"))
    now = [100.0]
    state_store = CallbackStateStore(
        settings.jwt_secret.get_secret_value(),
        clock=lambda: now[0],
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        callback = install_callback(app, settings, provider, state_store=state_store)
        without_cookie = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": "state-1"},
        )
        state = set_state_cookie(client, callback)
        mismatched = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": f"{state}-other"},
        )
        forged = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": "not-a-jwt"},
        )
        client.cookies.set(
            CALLBACK_STATE_COOKIE,
            "not-a-jwt",
            path="/api/auth",
        )
        forged_cookie = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": "not-a-jwt"},
        )
        unicode_state = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": "状态"},
        )
        state = set_state_cookie(client, callback)
        now[0] = 1_000.0
        expired = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": state},
        )

    for response in (without_cookie, mismatched, forged, forged_cookie, unicode_state, expired):
        assert response.status_code == 400
        assert response.json()["error"]["code"] == ErrorCode.AUTH_STATE_INVALID
    assert provider.calls == 0


async def test_callback_maps_missing_code_and_provider_rejection_to_401(
    tmp_path: Path,
) -> None:
    """A missing grant and a provider rejection share the invalid-credential code."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    provider = StubExternalProvider(None)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        callback = install_callback(app, settings, provider)
        state = set_state_cookie(client, callback)
        missing_code = await client.get(
            "/api/auth/callback",
            params={"state": state},
        )
        state = set_state_cookie(client, callback)
        rejected = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": state},
        )

    assert missing_code.status_code == 401
    assert missing_code.json()["error"]["code"] == ErrorCode.AUTH_INVALID
    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == ErrorCode.AUTH_INVALID
    assert provider.calls == 1


async def test_callback_never_creates_a_mapped_user_and_rejects_inactive_ones(
    tmp_path: Path,
) -> None:
    """An unknown subject is 403 with no insert; a disabled mapped account is 403."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    provider = StubExternalProvider(ProviderIdentity(AuthProviderName.OIDC, "unknown"))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        callback = install_callback(app, settings, provider)
        state = set_state_cookie(client, callback)
        unmapped = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": state},
        )
        users_after_unmapped = await app.state.identity.users.count()

        await map_user(app, "admin", is_active=False)
        provider.identity = ProviderIdentity(AuthProviderName.OIDC, "subject-1")
        state = set_state_cookie(client, callback)
        disabled = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": state},
        )

    assert unmapped.status_code == 403
    assert unmapped.json()["error"]["code"] == ErrorCode.AUTH_NO_MAPPING
    assert users_after_unmapped == 1
    assert disabled.status_code == 403
    assert disabled.json()["error"]["code"] == ErrorCode.FORBIDDEN


async def test_callback_maps_provider_exchange_failure_to_502(tmp_path: Path) -> None:
    """A provider transport or protocol failure is a gateway error, not a user error."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    provider = StubExternalProvider(error=AuthProviderError("exchange failed"))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        callback = install_callback(app, settings, provider)
        state = set_state_cookie(client, callback)
        response = await client.get(
            "/api/auth/callback",
            params={"code": "code-1", "state": state},
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == ErrorCode.AUTH_PROVIDER_ERROR


async def test_callback_shares_the_login_rate_limit(tmp_path: Path) -> None:
    """Repeated callback attempts consume the same per-IP login budget."""
    settings = identity_settings(tmp_path)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        responses = [await client.get("/api/auth/callback") for _ in range(11)]

    assert [response.status_code for response in responses[:10]] == [501] * 10
    assert responses[10].status_code == 429
    assert responses[10].json()["error"]["code"] == ErrorCode.RATE_LIMITED


async def test_only_the_seeded_administrator_can_hold_the_admin_role(
    tmp_path: Path,
) -> None:
    """Administrator provisioning cannot mint a second global admin."""
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
        await change_admin_password(client)
        refreshed = await client.post("/api/auth/refresh")
        headers = {"Authorization": f"Bearer {refreshed.json()['accessToken']}"}
        second_admin = await client.post(
            "/api/users",
            headers=headers,
            json={
                "username": "second-admin",
                "displayName": "Second Admin",
                "password": "temporary-password",
                "role": "admin",
            },
        )
        member = await client.post(
            "/api/users",
            headers=headers,
            json={
                "username": "member",
                "displayName": "Member",
                "password": "temporary-password",
                "role": "member",
            },
        )
        listed = await app.state.identity.users.list()

    assert second_admin.status_code == 422
    assert second_admin.json()["error"]["code"] == ErrorCode.ROLE_INVALID
    assert member.status_code == 201
    assert [record.role for record in listed].count("admin") == 1


async def test_auth_configuration_rejects_unsafe_cookie_and_oidc_values(
    tmp_path: Path,
) -> None:
    """Reserved provider settings still validate their future-facing shapes."""
    with pytest.raises(ValidationError, match="HE_SESSION_COOKIE_NAME"):
        identity_settings(tmp_path, session_cookie_name="bad cookie")
    with pytest.raises(ValidationError, match="HE_OIDC_ISSUER"):
        identity_settings(tmp_path, oidc_issuer="ftp://issuer.example")
    with pytest.raises(ValidationError, match="HE_OIDC_CLIENT_SECRET_ENV"):
        identity_settings(tmp_path, oidc_client_secret_env="not a name")
    configured = identity_settings(
        tmp_path,
        oidc_issuer="https://issuer.example",
        oidc_client_id="client-1",
        oidc_client_secret_env="HE_OIDC_SECRET",
    )
    assert configured.oidc_configured is True
