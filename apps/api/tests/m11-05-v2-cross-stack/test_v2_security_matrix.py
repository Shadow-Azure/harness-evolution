"""HTTP-level cross-workspace and role matrix over the V2 acceptance surface.

The matrix pins the V2 isolation contract from design 15 §8 and 02 §2.5:
invisible workspaces answer 404, visible-but-insufficient roles answer 403,
space administrators cannot mint or edit space administrators, and the global
administrator passes through every existing space.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import update

from app.db.models.domain import session_families
from tests.ingest.helpers import ingest_body
from tests.m10_02_potential_support import (
    LATER,
    NOW,
    seed_case,
    seed_event,
    seed_probe,
    seed_session,
    seed_target,
    seed_workspace,
)
from tests.v2_acceptance_support import (
    AcceptanceApi,
    Identity,
    seed_identity,
    seed_run,
)
from tests.v2_acceptance_support import acceptance_api as acceptance_api
from tests.workspaces.helpers import bearer

WORKSPACE_A = "ws-m11-05-a"
WORKSPACE_B = "ws-m11-05-b"
TARGET_A = "target-m11-05-a"
TARGET_B = "target-m11-05-b"
SESSION_A = "session-m11-05-a"
SESSION_B = "session-m11-05-b"
CASE_A = "case-m11-05-a"
CASE_B = "case-m11-05-b"
RUN_A = "run-m11-05-a"
RUN_B = "run-m11-05-b"
TARGET_NAME = "deep-research"
TARGET_VERSION = "v2.0.0"
WINDOW = "from=2026-11-01&to=2026-11-30"
OBJECT_ENTRY = NOW
CASE_ENTRY = LATER


@dataclass(frozen=True, slots=True)
class Matrix:
    """Two seeded spaces plus the identities and stable ids of the matrix."""

    api: AcceptanceApi
    identities: dict[str, Identity]
    credential_id: str
    credential: str
    revoked_credential: str


@dataclass(frozen=True, slots=True)
class WriteCase:
    """One space-admin write request with its body builder."""

    method: str
    path: Callable[[Matrix], str]
    body: Callable[[Matrix], dict[str, object] | None]


def _workspace_path(workspace_id: str, suffix: str = "") -> str:
    """Return one workspace-scoped URL suffix."""
    return f"/api/workspaces/{workspace_id}{suffix}"


READ_PATHS: dict[str, Callable[[Matrix], str]] = {
    "sessions": lambda _m: _workspace_path(WORKSPACE_A, "/sessions"),
    "session": lambda _m: _workspace_path(WORKSPACE_A, f"/sessions/{SESSION_A}"),
    "bad-cases": lambda _m: _workspace_path(WORKSPACE_A, "/bad-cases"),
    "bad-case": lambda _m: _workspace_path(WORKSPACE_A, f"/bad-cases/{CASE_A}"),
    "attributions": lambda _m: _workspace_path(
        WORKSPACE_A,
        f"/bad-cases/{CASE_A}/attributions",
    ),
    "overview-summary": lambda _m: _workspace_path(WORKSPACE_A, f"/overview/summary?{WINDOW}"),
    "overview-trend": lambda _m: _workspace_path(WORKSPACE_A, f"/overview/trend?{WINDOW}"),
    "overview-cases": lambda _m: _workspace_path(
        WORKSPACE_A,
        f"/overview/targets/cases?{WINDOW}",
    ),
    "overview-targets": lambda _m: _workspace_path(
        WORKSPACE_A,
        f"/overview/targets?{WINDOW}",
    ),
    "evolution-targets": lambda _m: _workspace_path(WORKSPACE_A, "/evolution/targets"),
    "evolution-runs": lambda _m: _workspace_path(WORKSPACE_A, "/evolution/runs"),
    "members": lambda _m: _workspace_path(WORKSPACE_A, "/members"),
    "credentials": lambda _m: _workspace_path(WORKSPACE_A, "/credentials"),
}

READ_ALLOWED: dict[str, frozenset[str]] = {
    "viewer": frozenset(READ_PATHS) - {"members", "credentials"},
    "member": frozenset(READ_PATHS) - {"credentials"},
    "space_admin": frozenset(READ_PATHS),
    "global_admin": frozenset(READ_PATHS),
}
READ_MATRIX: list[tuple[str, str, int]] = [
    (actor, path_key, 200 if path_key in allowed else 403)
    for actor, allowed in READ_ALLOWED.items()
    for path_key in sorted(READ_PATHS)
]


def _target_body(_m: Matrix) -> dict[str, object]:
    """Return one valid target configuration body."""
    return {
        "objectType": "skill",
        "objectName": "new-target",
        "repoUrl": "https://example.invalid/new-target.git",
        "subDir": "skills/new-target",
        "defaultRef": "v1.0.0",
        "validationProjectId": "validation-project",
        "testProjectId": "test-project",
        "enabled": True,
    }


def _run_body(_m: Matrix) -> dict[str, object]:
    """Return one valid launch request for the seeded target."""
    return {
        "targetType": "skill",
        "targetName": TARGET_NAME,
        "targetVersion": TARGET_VERSION,
        "from": "2026-11-01",
        "to": "2026-11-30",
        "mode": "full",
        "cacheEnabled": True,
    }


def _member_body(m: Matrix) -> dict[str, object]:
    """Return one valid add-member request for the unaffiliated candidate."""
    return {"userId": m.identities["candidate"].user_id, "role": "viewer"}


def _promote_body(m: Matrix) -> dict[str, object]:
    """Return one valid space-admin grant request for the promotable user."""
    return {"userId": m.identities["promotable"].user_id, "role": "space_admin"}


WRITE_CASES: dict[str, WriteCase] = {
    "update-workspace": WriteCase(
        "PUT",
        lambda _m: _workspace_path(WORKSPACE_A),
        lambda _m: {"quota": 50},
    ),
    "add-member": WriteCase(
        "POST",
        lambda _m: _workspace_path(WORKSPACE_A, "/members"),
        _member_body,
    ),
    "update-member": WriteCase(
        "PUT",
        lambda m: _workspace_path(
            WORKSPACE_A,
            f"/members/{m.identities['second_admin'].user_id}",
        ),
        lambda _m: {"role": "viewer"},
    ),
    "remove-member": WriteCase(
        "DELETE",
        lambda m: _workspace_path(
            WORKSPACE_A,
            f"/members/{m.identities['second_admin'].user_id}",
        ),
        lambda _m: None,
    ),
    "create-credential": WriteCase(
        "POST",
        lambda _m: _workspace_path(WORKSPACE_A, "/credentials"),
        lambda _m: None,
    ),
    "revoke-credential": WriteCase(
        "DELETE",
        lambda m: _workspace_path(WORKSPACE_A, f"/credentials/{m.credential_id}"),
        lambda _m: None,
    ),
    "create-target": WriteCase(
        "POST",
        lambda _m: _workspace_path(WORKSPACE_A, "/evolution/targets"),
        _target_body,
    ),
    "update-target": WriteCase(
        "PUT",
        lambda _m: _workspace_path(WORKSPACE_A, f"/evolution/targets/{TARGET_A}"),
        _target_body,
    ),
    "delete-target": WriteCase(
        "DELETE",
        lambda _m: _workspace_path(WORKSPACE_A, f"/evolution/targets/{TARGET_A}"),
        lambda _m: None,
    ),
    "create-run": WriteCase(
        "POST",
        lambda _m: _workspace_path(WORKSPACE_A, "/evolution/runs"),
        _run_body,
    ),
    "cluster-preview": WriteCase(
        "POST",
        lambda _m: _workspace_path(WORKSPACE_A, "/evolution/cluster-previews"),
        _run_body,
    ),
    "retry-run": WriteCase(
        "POST",
        lambda _m: _workspace_path(WORKSPACE_A, f"/evolution/runs/{RUN_A}/retry"),
        lambda _m: None,
    ),
}


async def _create_credential(
    api: AcceptanceApi,
    identity: Identity,
) -> tuple[str, str]:
    """Create one ingest credential and return its id and one-time plaintext."""
    response = await api.client.post(
        _workspace_path(WORKSPACE_A, "/credentials"),
        headers=identity.headers,
    )
    assert response.status_code == 201
    body = response.json()
    return str(body["credentialId"]), str(body["credential"])


async def _seed_matrix(api: AcceptanceApi) -> Matrix:
    """Seed two spaces, every tested role, and stable resources in each."""
    database = api.database
    await seed_workspace(database, WORKSPACE_A)
    await seed_workspace(database, WORKSPACE_B)
    identities = {
        "viewer": await seed_identity(
            api.app,
            database,
            username="m11-05-viewer",
            workspace_id=WORKSPACE_A,
            workspace_role="viewer",
        ),
        "member": await seed_identity(
            api.app,
            database,
            username="m11-05-member",
            workspace_id=WORKSPACE_A,
            workspace_role="member",
        ),
        "space_admin": await seed_identity(
            api.app,
            database,
            username="m11-05-space-admin",
            workspace_id=WORKSPACE_A,
            workspace_role="space_admin",
        ),
        "second_admin": await seed_identity(
            api.app,
            database,
            username="m11-05-second-admin",
            workspace_id=WORKSPACE_A,
            workspace_role="space_admin",
        ),
        "outsider": await seed_identity(
            api.app,
            database,
            username="m11-05-outsider",
            workspace_id=WORKSPACE_B,
            workspace_role="viewer",
        ),
        "candidate": await seed_identity(
            api.app,
            database,
            username="m11-05-candidate",
        ),
        "promotable": await seed_identity(
            api.app,
            database,
            username="m11-05-promotable",
        ),
        "global_admin": await seed_identity(
            api.app,
            database,
            username="m11-05-global-admin",
            global_role="admin",
        ),
    }
    await seed_target(
        database,
        workspace_id=WORKSPACE_A,
        target_id=TARGET_A,
        object_name=TARGET_NAME,
        default_ref=TARGET_VERSION,
    )
    await seed_target(
        database,
        workspace_id=WORKSPACE_B,
        target_id=TARGET_B,
        object_name=TARGET_NAME,
        default_ref=TARGET_VERSION,
    )
    for workspace_id, session_id, case_id in (
        (WORKSPACE_A, SESSION_A, CASE_A),
        (WORKSPACE_B, SESSION_B, CASE_B),
    ):
        main_id = await seed_session(
            database,
            session_id=session_id,
            started_at=NOW,
            title=session_id,
        )
        await seed_event(
            database,
            agent_id=main_id,
            event_index=0,
            kind="skill",
            name=TARGET_NAME,
            object_version=TARGET_VERSION,
            triggered_at=OBJECT_ENTRY,
        )
        await seed_case(
            database,
            case_id=case_id,
            session_id=session_id,
            workspace_id=workspace_id,
            case_type="self",
            object_name=TARGET_NAME,
            created_at=CASE_ENTRY,
        )
        await seed_probe(
            database,
            case_id=case_id,
            session_id=session_id,
            workspace_id=workspace_id,
        )
    async with database.transaction() as session:
        await session.execute(
            update(session_families)
            .where(session_families.c.id.in_((SESSION_A, SESSION_B)))
            .values(status="ok"),
        )
    await seed_run(database, run_id=RUN_A, workspace_id=WORKSPACE_A)
    await seed_run(database, run_id=RUN_B, workspace_id=WORKSPACE_B)

    credential_id, credential = await _create_credential(api, identities["space_admin"])
    revoked_id, revoked_credential = await _create_credential(
        api,
        identities["space_admin"],
    )
    revoked = await api.client.delete(
        _workspace_path(WORKSPACE_A, f"/credentials/{revoked_id}"),
        headers=identities["space_admin"].headers,
    )
    assert revoked.status_code == 204
    return Matrix(
        api=api,
        identities=identities,
        credential_id=credential_id,
        credential=credential,
        revoked_credential=revoked_credential,
    )


@pytest_asyncio.fixture
async def matrix(acceptance_api: AcceptanceApi) -> Matrix:
    """Seed and return the cross-workspace matrix fixture."""
    return await _seed_matrix(acceptance_api)


@pytest.mark.parametrize(
    ("actor", "path_key", "expected"),
    READ_MATRIX,
    ids=[f"{actor}-{path_key}" for actor, path_key, _ in READ_MATRIX],
)
async def test_v2_read_surface_role_matrix(
    matrix: Matrix,
    actor: str,
    path_key: str,
    expected: int,
) -> None:
    """Every V2 read is viewer-or-higher, with the documented per-route floors."""
    response = await matrix.api.client.get(
        READ_PATHS[path_key](matrix),
        headers=matrix.identities[actor].headers,
    )

    assert response.status_code == expected
    if expected == 403:
        assert response.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"


@pytest.mark.parametrize("path_key", sorted(READ_PATHS))
async def test_invisible_workspace_answers_404_not_403(
    matrix: Matrix,
    path_key: str,
) -> None:
    """A member of space B cannot enumerate space A through any V2 read."""
    response = await matrix.api.client.get(
        READ_PATHS[path_key](matrix),
        headers=matrix.identities["outsider"].headers,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


async def test_invisible_workspace_also_hides_writes(matrix: Matrix) -> None:
    """The invisible-space 404 precedes any write authorization decision."""
    response = await matrix.api.client.put(
        _workspace_path(WORKSPACE_A),
        headers=matrix.identities["outsider"].headers,
        json={"quota": 50},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


@pytest.mark.parametrize("actor", ["viewer", "member"])
@pytest.mark.parametrize("path_key", sorted(WRITE_CASES))
async def test_viewer_and_member_cannot_perform_space_admin_writes(
    matrix: Matrix,
    actor: str,
    path_key: str,
) -> None:
    """Both non-admin roles receive the same 403 for every administration write."""
    case = WRITE_CASES[path_key]
    body = case.body(matrix)
    if body is None:
        response = await matrix.api.client.request(
            case.method,
            case.path(matrix),
            headers=matrix.identities[actor].headers,
        )
    else:
        response = await matrix.api.client.request(
            case.method,
            case.path(matrix),
            headers=matrix.identities[actor].headers,
            json=body,
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"


async def test_space_admin_cannot_grant_or_change_space_admin(matrix: Matrix) -> None:
    """Granting space_admin is 403 while editing an existing row is 409."""
    api = matrix.api
    headers = matrix.identities["space_admin"].headers

    added = await api.client.post(
        _workspace_path(WORKSPACE_A, "/members"),
        headers=headers,
        json=_promote_body(matrix),
    )
    changed = await api.client.put(
        _workspace_path(
            WORKSPACE_A,
            f"/members/{matrix.identities['second_admin'].user_id}",
        ),
        headers=headers,
        json={"role": "viewer"},
    )
    removed = await api.client.delete(
        _workspace_path(
            WORKSPACE_A,
            f"/members/{matrix.identities['second_admin'].user_id}",
        ),
        headers=headers,
    )
    ordinary = await api.client.post(
        _workspace_path(WORKSPACE_A, "/members"),
        headers=headers,
        json=_member_body(matrix),
    )

    assert added.status_code == 403
    assert added.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "ROLE_LOCKED"
    assert removed.status_code == 409
    assert removed.json()["error"]["code"] == "ROLE_LOCKED"
    assert ordinary.status_code == 201


async def test_global_admin_manages_space_admin_rows(matrix: Matrix) -> None:
    """Only the global administrator renames a space, grants space_admin, and self-appoints."""
    api = matrix.api
    headers = matrix.identities["global_admin"].headers

    renamed = await api.client.put(
        _workspace_path(WORKSPACE_A),
        headers=headers,
        json={"name": "renamed-by-global-admin"},
    )
    granted = await api.client.post(
        _workspace_path(WORKSPACE_A, "/members"),
        headers=headers,
        json=_promote_body(matrix),
    )
    self_admin = await api.client.post(
        _workspace_path(WORKSPACE_A, "/members/self-admin"),
        headers=headers,
    )
    denied = await api.client.post(
        _workspace_path(WORKSPACE_A, "/members/self-admin"),
        headers=matrix.identities["space_admin"].headers,
    )

    assert renamed.status_code == 200
    assert granted.status_code == 201
    assert granted.json()["role"] == "space_admin"
    assert self_admin.status_code == 200
    assert self_admin.json()["role"] == "space_admin"
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"


async def test_ingest_credential_is_bound_to_its_workspace(matrix: Matrix) -> None:
    """Valid credentials write, cross-space credentials are 403, dead ones 401."""
    api = matrix.api

    accepted = await api.client.post(
        _workspace_path(WORKSPACE_A, "/bad-cases"),
        headers=bearer(matrix.credential),
        json=ingest_body(badCaseId="BC-M11-05-VALID"),
    )
    crossed = await api.client.post(
        _workspace_path(WORKSPACE_B, "/bad-cases"),
        headers=bearer(matrix.credential),
        json=ingest_body(badCaseId="BC-M11-05-CROSS"),
    )
    unknown = await api.client.post(
        _workspace_path(WORKSPACE_A, "/bad-cases"),
        headers=bearer("whk_unknown"),
        json=ingest_body(badCaseId="BC-M11-05-UNKNOWN"),
    )
    revoked = await api.client.post(
        _workspace_path(WORKSPACE_A, "/bad-cases"),
        headers=bearer(matrix.revoked_credential),
        json=ingest_body(badCaseId="BC-M11-05-REVOKED"),
    )

    assert accepted.status_code == 201
    assert crossed.status_code == 403
    assert crossed.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "CREDENTIAL_INVALID"
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "CREDENTIAL_INVALID"


async def test_foreign_ids_stay_invisible_inside_a_visible_workspace(
    matrix: Matrix,
) -> None:
    """Ids owned by space B never resolve through space A reads or lists."""
    api = matrix.api
    headers = matrix.identities["viewer"].headers
    probes = {
        "session": f"/sessions/{SESSION_B}",
        "bad-case": f"/bad-cases/{CASE_B}",
        "attributions": f"/bad-cases/{CASE_B}/attributions",
        "target-detail": f"/overview/targets/{TARGET_B}/detail?{WINDOW}",
        "foreign-attribution": f"/bad-cases/{CASE_A}/attributions/probe-{CASE_B}",
        "run": f"/evolution/runs/{RUN_B}",
    }

    for suffix in probes.values():
        response = await api.client.get(
            _workspace_path(WORKSPACE_A, suffix),
            headers=headers,
        )
        assert response.status_code == 404

    legacy = await api.client.get(f"/api/sessions/{SESSION_B}", headers=headers)
    assert legacy.status_code == 404

    sessions = await api.client.get(
        _workspace_path(WORKSPACE_A, "/sessions"),
        headers=headers,
    )
    bad_cases = await api.client.get(
        _workspace_path(WORKSPACE_A, "/bad-cases"),
        headers=headers,
    )
    targets = await api.client.get(
        _workspace_path(WORKSPACE_A, "/evolution/targets"),
        headers=headers,
    )
    runs = await api.client.get(
        _workspace_path(WORKSPACE_A, "/evolution/runs"),
        headers=headers,
    )
    cases = await api.client.get(
        _workspace_path(WORKSPACE_A, f"/overview/targets/cases?{WINDOW}&targets={TARGET_B}"),
        headers=headers,
    )

    assert {item["id"] for item in sessions.json()["items"]} == {SESSION_A}
    assert {item["badCaseId"] for item in bad_cases.json()["items"]} == {CASE_A}
    assert {item["id"] for item in targets.json()["items"]} == {TARGET_A}
    assert {card["runId"] for card in runs.json()["running"] + runs.json()["history"]} == {RUN_A}
    assert cases.json()["total"] == 0
