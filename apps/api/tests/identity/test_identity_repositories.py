"""User and ticket behavior behind the identity service."""

from pathlib import Path

import pytest

from app.errors import AppError
from app.main import create_app
from app.service.events import ShapeRunTopicAuthorizer
from app.service.identity.tickets import TicketStore
from app.service.identity.tokens import TokenService
from tests.identity.helpers import change_admin_password, identity_settings, login


async def test_admin_can_create_and_list_users_without_password_material(
    tmp_path: Path,
) -> None:
    """Admin user management returns public users only and normalizes usernames."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        await change_admin_password(client)
        await client.post("/api/auth/refresh")
        access = (await login(client, password="replacement-password")).json()["accessToken"]
        headers = {"Authorization": f"Bearer {access}"}

        created = await client.post(
            "/api/users",
            headers=headers,
            json={
                "username": "Alice",
                "displayName": "Alice",
                "password": "temporary-password",
                "role": "member",
            },
        )
        listed = await client.get("/api/users", headers=headers)
        duplicate = await client.post(
            "/api/users",
            headers=headers,
            json={
                "username": "ALICE",
                "displayName": "Alice Duplicate",
                "password": "temporary-password",
                "role": "member",
            },
        )
        normalized_login = await login(
            client,
            username="ALICE",
            password="temporary-password",
        )

    assert created.status_code == 201
    assert created.json()["mustChangePassword"] is True
    assert "password" not in created.json()
    assert listed.status_code == 200
    assert listed.json()["items"][0]["username"] == "admin"
    assert listed.json()["items"][1]["username"] == "alice"
    for user in listed.json()["items"]:
        assert "password" not in user
        assert "passwordHash" not in user
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "USERNAME_CONFLICT"
    assert normalized_login.status_code == 200
    assert normalized_login.json()["user"]["username"] == "alice"


async def test_event_tickets_reject_invalid_topics_and_expired_grants(tmp_path: Path) -> None:
    """Topic validation and elapsed TTL both map to stable ticket failures."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        await change_admin_password(client)
        await client.post("/api/auth/refresh")
        access = (await login(client, password="replacement-password")).json()["accessToken"]
        invalid = await client.post(
            "/api/events/ticket",
            headers={"Authorization": f"Bearer {access}"},
            json={"topics": ["sync:not-allowed"]},
        )
        expired_store = TicketStore(ttl_seconds=0)
        expired_ticket = expired_store.issue(
            user_id="user-1",
            topics=("run:evolution-1",),
            last_event_id=3,
        )
        with pytest.raises(AppError) as expired:
            expired_store.consume(expired_ticket)

    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "TICKET_INVALID"
    assert expired.value.status_code == 401
    assert expired.value.code == "TICKET_EXPIRED"


async def test_event_ticket_is_bound_to_run_topics_and_single_use(tmp_path: Path) -> None:
    """The in-memory ticket store binds topics once and rejects replayed grants."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    app.state.run_topic_authorizer = ShapeRunTopicAuthorizer()
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        await change_admin_password(client)
        await client.post("/api/auth/refresh")
        access = (await login(client, password="replacement-password")).json()["accessToken"]
        response = await client.post(
            "/api/events/ticket",
            headers={"Authorization": f"Bearer {access}"},
            json={"topics": ["run:evolution-1"], "lastEventId": 7},
        )
        ticket_store = app.state.identity.tickets
        grant = ticket_store.consume(response.json()["ticket"])
        with pytest.raises(AppError) as replay:
            ticket_store.consume(response.json()["ticket"])

    assert response.status_code == 200
    assert response.json() == {
        "ticket": response.json()["ticket"],
        "expiresIn": 60,
        "topics": ["run:evolution-1"],
    }
    assert grant.topics == ("run:evolution-1",)
    assert grant.last_event_id == 7
    assert replay.value.status_code == 401
    assert replay.value.code == "TICKET_INVALID"


def test_ticket_store_rejects_multiple_topics() -> None:
    """The M1 single integer cursor cannot safely resume multiple run topics."""
    store = TicketStore()

    with pytest.raises(AppError) as invalid:
        store.issue(
            user_id="user-1",
            topics=("run:a", "run:b"),
            last_event_id=0,
        )

    assert invalid.value.status_code == 401
    assert invalid.value.code == "TICKET_INVALID"


async def test_event_ticket_is_bound_to_the_issuing_user(tmp_path: Path) -> None:
    """A ticket grant carries the authenticated principal that requested it."""
    settings = identity_settings(
        tmp_path,
        admin_username="admin",
        admin_password="initial-password",
    )
    app = create_app(settings)
    app.state.run_topic_authorizer = ShapeRunTopicAuthorizer()
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        await change_admin_password(client)
        await client.post("/api/auth/refresh")
        authenticated = await login(client, password="replacement-password")
        user_id = authenticated.json()["user"]["id"]
        access = authenticated.json()["accessToken"]
        response = await client.post(
            "/api/events/ticket",
            headers={"Authorization": f"Bearer {access}"},
            json={"topics": ["run:evolution-1"]},
        )
        grant = app.state.identity.tickets.consume(response.json()["ticket"])

    assert grant.user_id == user_id


def test_self_describing_ticket_remains_expired_after_grant_cleanup() -> None:
    """A signed expiry outlives in-memory grants and preserves the stable error code."""
    now = [100.0]
    store = TicketStore(ttl_seconds=60, clock=lambda: now[0])
    old_ticket = store.issue(user_id="user-1", topics=("run:old",), last_event_id=0)
    now[0] = 161.0
    store.issue(user_id="user-1", topics=("run:new",), last_event_id=0)
    now[0] = 10_000.0

    assert store.active_count == 0
    with pytest.raises(AppError) as expired:
        store.consume(old_ticket)
    assert expired.value.code == "TICKET_EXPIRED"


def test_tampered_ticket_is_invalid_even_if_its_expiry_is_in_the_past() -> None:
    """Clients cannot fabricate an expired ticket by editing an issued value."""
    now = [100.0]
    store = TicketStore(ttl_seconds=60, clock=lambda: now[0])
    ticket = store.issue(user_id="user-1", topics=("run:old",), last_event_id=0)
    tampered = f"{ticket[:-1]}{'A' if ticket[-1] != 'A' else 'B'}"

    with pytest.raises(AppError) as invalid:
        store.consume(tampered)
    assert invalid.value.code == "TICKET_INVALID"


def test_non_ascii_ticket_signature_is_invalid_instead_of_raising() -> None:
    """Malformed client text cannot escape as TypeError from constant-time comparison."""
    store = TicketStore()

    with pytest.raises(AppError) as invalid:
        store.consume("abc.123.é")

    assert invalid.value.status_code == 401
    assert invalid.value.code == "TICKET_INVALID"


async def test_refresh_revocations_expire_without_unbounded_growth() -> None:
    """Successful rotations and logout revocations are pruned after token expiry."""
    from app.service.identity.revocations import RefreshRevocationStore

    now = [100.0]
    store = RefreshRevocationStore(clock=lambda: now[0])
    assert await store.consume_once("first", expires_at=160.0) is True
    assert await store.consume_once("first", expires_at=160.0) is False
    assert store.active_count == 1

    now[0] = 161.0
    assert await store.consume_once("second", expires_at=220.0) is True
    assert store.active_count == 1


async def test_refresh_tokens_carry_a_bounded_revocation_deadline(tmp_path: Path) -> None:
    """Refresh grants expose their signed expiry so the replay index can self-clean."""
    settings = identity_settings(tmp_path)
    grant = TokenService(settings).decode_refresh_token(
        TokenService(settings).create_refresh_token(user_id="user-1")
    )

    assert grant.expires_at.timestamp() > 0
