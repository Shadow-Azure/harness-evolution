"""Target validation, service orchestration, and Git remote adapter contracts."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution_targets import (
    EvolutionTargetConflict,
    EvolutionTargetInUse,
    EvolutionTargetRecord,
    EvolutionTargetRepository,
)
from app.db.models.domain import evolution_targets
from app.db.models.evolution import evolution_runs
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.errors import AppError, ErrorCode
from app.main import create_app
from app.service.evolution.targets import (
    EvolutionTargetService,
    EvolutionTargetWrite,
)
from app.third_party_api.git.content import GitContentUnavailable
from app.third_party_api.git.remote import (
    GitProcessResult,
    RepoInvalid,
    SubprocessGitRemote,
)
from app.utils.redaction import redact_command_output
from tests.target_content_support import FakeDefinitionSource
from tests.workspaces.helpers import insert_member

TARGET_ADMIN_TEMP_PASSWORD = "admin-target-temp-password"
TARGET_ADMIN_PASSWORD = "admin-target-password"
TARGET_MEMBER_TEMP_PASSWORD = "member-target-temp-password"
TARGET_MEMBER_PASSWORD = "member-target-password"


class FakeRepository:
    """In-memory target persistence for service orchestration tests."""

    def __init__(self) -> None:
        """Start with no configured rows."""
        self.rows: dict[str, EvolutionTargetRecord] = {}
        self.active = False
        self.next_id = 1

    async def list(
        self,
        *,
        enabled_only: bool = False,
        workspace_ids: Sequence[str] | None = None,
    ) -> tuple[EvolutionTargetRecord, ...]:
        """Return rows using the production order."""
        rows = sorted(
            self.rows.values(),
            key=lambda row: (row.object_type, row.object_name, row.id),
        )
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        if workspace_ids is not None:
            rows = [row for row in rows if row.workspace_id in workspace_ids]
        return tuple(rows)

    async def get(
        self,
        target_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord | None:
        """Return one stored row inside the optional workspace scope."""
        row = self.rows.get(target_id)
        if row is None or workspace_ids is None:
            return row
        return row if row.workspace_id in workspace_ids else None

    async def find(
        self,
        object_type: str,
        object_name: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord | None:
        """Find a row by the unique object pair inside the optional scope."""
        rows = await self.find_all(
            object_type,
            object_name,
            workspace_ids=workspace_ids,
        )
        return rows[0] if rows else None

    async def find_all(
        self,
        object_type: str,
        object_name: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> tuple[EvolutionTargetRecord, ...]:
        """Return every matching pair inside the optional scope."""
        rows = [
            row
            for row in self.rows.values()
            if row.object_type == object_type
            and row.object_name == object_name
            and (workspace_ids is None or row.workspace_id in workspace_ids)
        ]
        return tuple(sorted(rows, key=lambda row: (row.workspace_id, row.id)))

    async def insert(self, values: Mapping[str, object]) -> EvolutionTargetRecord:
        """Insert or raise the production conflict type."""
        if await self.find(str(values["object_type"]), str(values["object_name"])):
            raise EvolutionTargetConflict
        target_id = f"target-{self.next_id}"
        self.next_id += 1
        row = _record(target_id, values)
        self.rows[target_id] = row
        return row

    async def update(
        self,
        target_id: str,
        values: Mapping[str, object],
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord:
        """Replace editable fields or raise the production missing/conflict errors."""
        row = self.rows.get(target_id)
        if row is None or (workspace_ids is not None and row.workspace_id not in workspace_ids):
            raise LookupError("missing")
        existing = await self.find(
            str(values["object_type"]),
            str(values["object_name"]),
            workspace_ids=(row.workspace_id,),
        )
        if existing is not None and existing.id != target_id:
            raise EvolutionTargetConflict
        row = _record(target_id, values)
        self.rows[target_id] = row
        return row

    async def delete(
        self,
        target_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> bool:
        """Delete and report whether an in-scope row existed."""
        if self.active:
            raise EvolutionTargetInUse
        row = self.rows.get(target_id)
        if row is None or (workspace_ids is not None and row.workspace_id not in workspace_ids):
            return False
        return self.rows.pop(target_id, None) is not None

    async def has_active_runs(self, target_id: str) -> bool:
        """Return the scenario-configured active-run flag."""
        return self.active


def _record(target_id: str, values: Mapping[str, object]) -> EvolutionTargetRecord:
    """Build one record without importing persistence-only defaults."""
    return EvolutionTargetRecord(
        id=target_id,
        object_type=values["object_type"],  # type: ignore[arg-type]
        object_name=str(values["object_name"]),
        repo_url=str(values["repo_url"]),
        sub_dir=str(values["sub_dir"]),
        default_ref=str(values["default_ref"]),
        validation_project_id=str(values["validation_project_id"]),
        test_project_id=str(values["test_project_id"]),
        enabled=bool(values["enabled"]),
        workspace_id=str(values.get("workspace_id", DEFAULT_WORKSPACE_ID)),
    )


def _write(**overrides: Any) -> EvolutionTargetWrite:
    """Build a valid request with targeted overrides."""
    values: dict[str, Any] = {
        "object_type": "skill",
        "object_name": " deep-research ",
        "repo_url": "https://git.example.com/agent-skills.git",
        "sub_dir": " skills/deep-research ",
        "default_ref": " main ",
        "validation_project_id": " val-2026-q3 ",
        "test_project_id": " test-2026-q3 ",
        "enabled": True,
    }
    values.update(overrides)
    return EvolutionTargetWrite(**values)


def _project_payload(**overrides: Any) -> dict[str, Any]:
    """Build one camelCase target payload including both project IDs."""
    values: dict[str, Any] = {
        "objectType": "skill",
        "objectName": "deep-research",
        "repoUrl": "https://git.example.com/agent-skills.git",
        "subDir": "skills/deep-research",
        "defaultRef": "main",
        "validationProjectId": " val-2026-q3 ",
        "testProjectId": " test-2026-q3 ",
        "enabled": True,
    }
    values.update(overrides)
    return values


class FakeGitRemote:
    """Record remote calls and return configured tags or one failure."""

    def __init__(
        self,
        *,
        fail: bool = False,
        tags: tuple[str, ...] = ("v2.0.0", "v1.9.0"),
        failure: RepoInvalid | None = None,
    ) -> None:
        """Configure behavior for one service test."""
        self.fail = fail
        self.tags = tags
        self.failure = failure or RepoInvalid("token=should-not-leak")
        self.validated: list[tuple[str, str]] = []
        self.listed: list[str] = []

    async def validate(self, repo_url: str, ref: str) -> None:
        """Record validation or raise a sanitized remote failure."""
        self.validated.append((repo_url, ref))
        if self.fail:
            raise self.failure

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Record tag listing or raise a sanitized remote failure."""
        self.listed.append(repo_url)
        if self.fail:
            raise self.failure
        return self.tags


@dataclass(frozen=True, slots=True)
class TargetHttpEnvironment:
    """Authenticated clients and the fake remote used by one ASGI application."""

    admin: httpx.AsyncClient
    member: httpx.AsyncClient
    database: Database
    remote: FakeGitRemote


async def _complete_login(
    client: httpx.AsyncClient,
    *,
    username: str,
    old_password: str,
    new_password: str,
) -> None:
    """Complete the forced-password-change flow and install a bearer token."""
    login = await client.post(
        "/api/auth/login",
        json={"username": username, "password": old_password},
    )
    assert login.status_code == 200
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
        json={"oldPassword": old_password, "newPassword": new_password},
    )
    assert changed.status_code == 204
    relogin = await client.post(
        "/api/auth/login",
        json={"username": username, "password": new_password},
    )
    assert relogin.status_code == 200
    client.headers["Authorization"] = f"Bearer {relogin.json()['accessToken']}"


@pytest_asyncio.fixture
async def target_http(
    tmp_path: Path, request: pytest.FixtureRequest
) -> AsyncIterator[TargetHttpEnvironment]:
    """Provide member/admin clients over one application with a fake git remote."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        attribution_package_dir=tmp_path / "attribute",
        ai_agent_provider=getattr(request, "param", "fake"),
        attribution_bwrap_enabled=False,
        jwt_secret=SecretStr("target-http-signing-secret-with-sufficient-length"),
        admin_username="admin",
        admin_password=SecretStr(TARGET_ADMIN_TEMP_PASSWORD),
    )
    remote = FakeGitRemote(tags=("v2.0.0", "v1.9.0"))
    app = create_app(settings, git_remote=remote, definition_source=FakeDefinitionSource())
    transport = httpx.ASGITransport(app=app)
    admin = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    member = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            member_record = await app.state.identity.create_user(
                username="member",
                display_name="Member",
                password=TARGET_MEMBER_TEMP_PASSWORD,
                role="member",
            )
            await insert_member(
                app.state.database,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id=member_record.id,
                role="viewer",
            )
            await _complete_login(
                admin,
                username="admin",
                old_password=TARGET_ADMIN_TEMP_PASSWORD,
                new_password=TARGET_ADMIN_PASSWORD,
            )
            await _complete_login(
                member,
                username="member",
                old_password=TARGET_MEMBER_TEMP_PASSWORD,
                new_password=TARGET_MEMBER_PASSWORD,
            )
            yield TargetHttpEnvironment(
                admin=admin,
                member=member,
                database=app.state.database,
                remote=remote,
            )
    finally:
        await member.aclose()
        await admin.aclose()


async def test_target_routes_round_trip_with_camel_case_and_member_reads(
    target_http: TargetHttpEnvironment,
) -> None:
    """The real ASGI app exposes CRUD, disabled config rows, and versions."""
    created = await target_http.admin.post(
        "/api/evolution/targets",
        json=_write().model_dump(by_alias=True),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["objectType"] == "skill"
    assert body["attributionPackageId"] is None
    assert body["definition"] is None
    assert body["objectName"] == "deep-research"
    assert body["repoUrl"] == "https://git.example.com/agent-skills.git"
    assert target_http.remote.validated == [
        (
            "https://git.example.com/agent-skills.git",
            "main",
        )
    ]

    listed = await target_http.member.get("/api/evolution/targets")
    assert listed.status_code == 200
    assert listed.json()["items"] == [body]

    update_body = _write(enabled=False).model_dump(by_alias=True)
    update_body["subDir"] = "skills/deep-research-v2"
    updated = await target_http.admin.put(
        f"/api/evolution/targets/{body['id']}",
        json=update_body,
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["subDir"] == "skills/deep-research-v2"
    disabled_list = await target_http.member.get("/api/evolution/targets")
    assert disabled_list.status_code == 200
    assert disabled_list.json()["items"][0]["enabled"] is False

    versions = await target_http.member.get(
        f"/api/evolution/targets/{body['id']}/versions",
    )
    assert versions.status_code == 200
    assert versions.json() == {
        "versions": ["v1.9.0", "v2.0.0"],
        "defaultRef": "main",
    }

    deleted = await target_http.admin.delete(
        f"/api/evolution/targets/{body['id']}",
    )
    assert deleted.status_code == 204
    assert deleted.content == b""


@pytest.mark.parametrize(
    ("target_http", "runtime_enabled"),
    [("fake", False), ("claude-code", True)],
    indirect=["target_http"],
    ids=["rules", "agent"],
)
async def test_new_target_uses_deployment_default_only_when_enabled(
    target_http: TargetHttpEnvironment,
    runtime_enabled: bool,
) -> None:
    """Older clients can omit a package on both rule and agent deployments."""
    response = await target_http.admin.get(
        f"/api/workspaces/{DEFAULT_WORKSPACE_ID}/attribution-skill-packages"
    )
    assert response.status_code == 200
    assert response.json()["runtimeEnabled"] is runtime_enabled
    payload = _project_payload(enabled=False)
    result = await target_http.admin.post("/api/evolution/targets", json=payload)
    assert result.status_code == 201
    target = result.json()
    assert target["attributionPackageId"] == (
        "default-attribute-badcases" if runtime_enabled else None
    )
    assert (target["definition"] is not None) == runtime_enabled


async def test_definition_is_pinned_before_binding_and_failed_edit_preserves_it(
    target_http: TargetHttpEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _write().model_dump(by_alias=True)
    payload.update(
        objectType="agent",
        objectName="code-generator",
        subDir="agents/code-generator",
        attributionPackageId="default-attribute-badcases",
    )
    endpoint = "/api/evolution/targets"
    commit = "a" * 40
    body = "---\nname: code-generator\n---\nGenerate code."

    async def read(
        source: object, *, repo_url: str, sub_dir: str, ref: str, file_name: str
    ) -> tuple[str, str]:
        assert repo_url == payload["repoUrl"].strip() and ref == payload["defaultRef"].strip()
        if file_name != "agent.md" or sub_dir != "agents/code-generator":
            raise GitContentUnavailable("file_not_found")
        return body, commit

    monkeypatch.setattr(FakeDefinitionSource, "read_file_at_commit", read)
    rejected = await target_http.admin.post(endpoint, json={**payload, "subDir": "missing"})
    assert rejected.status_code == 422
    assert (await target_http.admin.get(endpoint)).json()["items"] == []
    saved = await target_http.admin.post(endpoint, json=payload)
    assert saved.status_code == 201
    target = saved.json()
    assert target["definition"] == dict(
        commit=commit, path="agents/code-generator/agent.md", preview=body
    )
    folder = tmp_path / "attribute/ws-default/attribute_source"

    async def generation() -> str:
        async with target_http.database.session() as session:
            return str(
                await session.scalar(
                    select(evolution_targets.c.attribution_generation).where(
                        evolution_targets.c.id == target["id"]
                    )
                )
            )

    first_generation = await generation()
    original = folder / sha256(body.encode()).hexdigest() / "definition.md"
    assert original.read_text() == body
    endpoint += "/" + target["id"]
    assert (
        await target_http.admin.put(endpoint, json={**payload, "subDir": "missing"})
    ).status_code == 422
    assert await generation() == first_generation
    assert (await target_http.admin.put(endpoint, json=payload)).status_code == 200
    assert await generation() == first_generation
    commit = "b" * 40
    body = body.replace("name:", "description:")
    changed = await target_http.admin.put(endpoint, json=payload)
    assert changed.json()["definition"]["commit"] == commit
    assert await generation() != first_generation
    assert original.read_text() == target["definition"]["preview"]
    assert (folder / sha256(body.encode()).hexdigest() / "definition.md").read_text() == body


def test_target_write_schema_requires_project_ids() -> None:
    """The public write schema marks both project IDs as required inputs."""
    schema = EvolutionTargetWrite.model_json_schema(by_alias=True)

    assert {
        "validationProjectId",
        "testProjectId",
    } <= set(schema["required"])


async def test_target_project_ids_are_required_and_round_trip(
    target_http: TargetHttpEnvironment,
) -> None:
    """Both project IDs trim, persist, list, and survive a partial update."""
    created = await target_http.admin.post(
        "/api/evolution/targets",
        json=_project_payload(),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["validationProjectId"] == "val-2026-q3"
    assert body["testProjectId"] == "test-2026-q3"

    listed = await target_http.member.get("/api/evolution/targets")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["validationProjectId"] == "val-2026-q3"
    assert listed.json()["items"][0]["testProjectId"] == "test-2026-q3"

    updated = await target_http.admin.put(
        f"/api/evolution/targets/{body['id']}",
        json=_project_payload(validationProjectId=" val-v2 "),
    )
    assert updated.status_code == 200
    assert updated.json()["validationProjectId"] == "val-v2"
    assert updated.json()["testProjectId"] == "test-2026-q3"

    async with target_http.database.session() as session:
        row = (
            (
                await session.execute(
                    select(evolution_targets).where(
                        evolution_targets.c.id == body["id"],
                    ),
                )
            )
            .mappings()
            .one()
        )
    assert row["validation_project_id"] == "val-v2"
    assert row["test_project_id"] == "test-2026-q3"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("validationProjectId", "", "project_id_required"),
        ("testProjectId", "   ", "project_id_required"),
        ("validationProjectId", "val 2026", "project_id_format"),
        ("testProjectId", "test\t2026", "project_id_format"),
        ("testProjectId", "test\x00-2026", "project_id_format"),
    ],
)
async def test_target_project_ids_reject_empty_or_whitespace(
    target_http: TargetHttpEnvironment,
    field: str,
    value: str,
    reason: str,
) -> None:
    """Blank, whitespace-bearing, and control-bearing project IDs are rejected."""
    payload = _project_payload(**{field: value})
    response = await target_http.admin.post(
        "/api/evolution/targets",
        json=payload,
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "PROJECT_ID_INVALID"
    assert error["details"] == {"field": field, "reason": reason}
    assert error["message"] == "test project id is invalid"
    listed = await target_http.member.get("/api/evolution/targets")
    assert listed.json()["items"] == []


async def test_target_project_ids_are_required_when_the_key_is_missing(
    target_http: TargetHttpEnvironment,
) -> None:
    """Omitting a project ID is one stable 422 rather than a generic validation error."""
    payload = _project_payload()
    del payload["testProjectId"]
    response = await target_http.admin.post(
        "/api/evolution/targets",
        json=payload,
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "PROJECT_ID_INVALID"
    assert error["details"]["field"] == "testProjectId"
    assert error["details"]["reason"] == "project_id_required"


async def test_legacy_target_project_ids_are_empty_and_must_be_filled(
    target_http: TargetHttpEnvironment,
) -> None:
    """Rows migrated with empty IDs stay readable but cannot be saved empty."""
    async with target_http.database.transaction() as session:
        await session.execute(
            insert(evolution_targets).values(
                id="legacy-target",
                object_type="skill",
                object_name="legacy-skill",
                repo_url="https://git.example.com/legacy.git",
                sub_dir="skills/legacy",
                default_ref="main",
                enabled=True,
                created_by=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        )

    listed = await target_http.admin.get("/api/evolution/targets")
    assert listed.status_code == 200
    legacy = listed.json()["items"][0]
    assert legacy["validationProjectId"] == ""
    assert legacy["testProjectId"] == ""

    empty = await target_http.admin.put(
        "/api/evolution/targets/legacy-target",
        json=_project_payload(
            objectName="legacy-skill",
            repoUrl="https://git.example.com/legacy.git",
            subDir="skills/legacy",
            validationProjectId="",
            testProjectId="",
        ),
    )
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "PROJECT_ID_INVALID"

    filled = await target_http.admin.put(
        "/api/evolution/targets/legacy-target",
        json=_project_payload(
            objectName="legacy-skill",
            repoUrl="https://git.example.com/legacy.git",
            subDir="skills/legacy",
        ),
    )
    assert filled.status_code == 200
    assert filled.json()["validationProjectId"] == "val-2026-q3"


async def test_target_routes_preserve_admin_and_error_envelopes(
    target_http: TargetHttpEnvironment,
) -> None:
    """Write authorization and stable target errors are enforced at the edge."""
    denial = await target_http.member.post(
        "/api/evolution/targets",
        json=_write().model_dump(by_alias=True),
    )
    assert denial.status_code == 403
    assert denial.json()["error"]["code"] == "FORBIDDEN"

    invalid = await target_http.admin.post(
        "/api/evolution/targets",
        json=_write(repo_url="http://git.example.com/repo.git").model_dump(
            by_alias=True,
        ),
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "REPO_INVALID"
    assert invalid.json()["error"]["details"] == {
        "field": "repoUrl",
        "reason": "repo_url_format",
    }

    created = await target_http.admin.post(
        "/api/evolution/targets",
        json=_write().model_dump(by_alias=True),
    )
    duplicate = await target_http.admin.post(
        "/api/evolution/targets",
        json=_write().model_dump(by_alias=True),
    )
    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "TARGET_EXISTS"

    repository = EvolutionTargetRepository(target_http.database)
    target = await repository.find("skill", "deep-research")
    assert target is not None
    async with target_http.database.transaction() as session:
        await session.execute(
            insert(evolution_runs).values(
                id="target-in-use-run",
                title="target-in-use",
                mode="full",
                engine_key="full",
                eval_config={},
                target_config_id=target.id,
                target_type="skill",
                target_name=target.object_name,
                target_version="v1",
                repo_url=target.repo_url,
                sub_dir=target.sub_dir,
                remote_name="origin",
                push_status="pending",
                models=[],
                status="running",
                retry_attempts=0,
                eval_status="pending",
                progress_unit=0,
                stats={},
                created_at=datetime.now(UTC),
            ),
        )
    in_use = await target_http.admin.delete(
        f"/api/evolution/targets/{created.json()['id']}",
    )
    assert in_use.status_code == 409
    assert in_use.json()["error"]["code"] == "TARGET_IN_USE"

    missing = await target_http.admin.delete("/api/evolution/targets/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TARGET_NOT_FOUND"


async def test_overlong_target_fields_return_field_details(
    target_http: TargetHttpEnvironment,
) -> None:
    """Overlong editable fields reach the service and report REPO_INVALID details."""
    response = await target_http.admin.post(
        "/api/evolution/targets",
        json=_project_payload(objectName="x" * 129),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REPO_INVALID"
    assert response.json()["error"]["details"] == {
        "field": "objectName",
        "reason": "object_name_invalid",
    }


async def test_remote_diagnostics_reach_admin_writes_only(
    target_http: TargetHttpEnvironment,
) -> None:
    """Admin writes receive redacted output; member versions stay details-free."""
    created = await target_http.admin.post(
        "/api/evolution/targets",
        json=_project_payload(),
    )
    assert created.status_code == 201
    target_id = created.json()["id"]

    target_http.remote.fail = True
    target_http.remote.failure = RepoInvalid(
        reason="repo_unreachable",
        exit_code=128,
        stderr=(
            "fatal: unable to access "
            "'https://bob:hunter2@git.example.com/repo.git/': "
            "Could not resolve host\n"
            "error: could not read /Users/alice/.ssh/id_rsa"
        ),
    )
    update = await target_http.admin.put(
        f"/api/evolution/targets/{target_id}",
        json=_project_payload(subDir="skills/renamed"),
    )
    assert update.status_code == 422
    details = update.json()["error"]["details"]
    assert details["field"] == "repoUrl"
    assert details["reason"] == "repo_unreachable"
    assert details["command"] == {"name": "git ls-remote", "exitCode": 128}
    assert "Could not resolve host" in details["output"]
    assert "hunter2" not in details["output"]
    assert "/Users/alice" not in details["output"]

    versions = await target_http.member.get(
        f"/api/evolution/targets/{target_id}/versions",
    )
    assert versions.status_code == 422
    assert versions.json()["error"]["code"] == "REPO_INVALID"
    assert versions.json()["error"]["details"] == {}


async def test_target_delete_allows_history_and_clears_only_the_fk(
    target_http: TargetHttpEnvironment,
) -> None:
    """Terminal runs preserve snapshots while releasing the deleted target FK."""
    created = await target_http.admin.post(
        "/api/evolution/targets",
        json=_write().model_dump(by_alias=True),
    )
    assert created.status_code == 201
    target_id = created.json()["id"]
    async with target_http.database.transaction() as session:
        await session.execute(
            insert(evolution_runs).values(
                id="target-history-run",
                title="target-history",
                mode="full",
                engine_key="full",
                eval_config={},
                target_config_id=target_id,
                target_type="skill",
                target_name="deep-research",
                target_version="v1",
                repo_url="https://git.example.com/agent-skills.git",
                sub_dir="skills/deep-research",
                remote_name="origin",
                push_status="succeeded",
                models=[],
                status="completed",
                retry_attempts=0,
                eval_status="completed",
                progress_unit=5,
                stats={},
                created_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
            ),
        )

    deleted = await target_http.admin.delete(
        f"/api/evolution/targets/{target_id}",
    )

    assert deleted.status_code == 204
    async with target_http.database.session() as session:
        target_config_id: str | None = (
            await session.execute(
                select(evolution_runs.c.target_config_id).where(
                    evolution_runs.c.id == "target-history-run",
                ),
            )
        ).scalar_one()
    assert target_config_id is None


@pytest.mark.parametrize(
    "repo_url",
    [
        "https://git.example.com/agent-skills.git",
        "ssh://git@git.example.com:2222/agent-skills.git",
        "git@git.example.com:agent-skills.git",
    ],
)
async def test_valid_repo_forms_are_normalized_and_validated(repo_url: str) -> None:
    """Supported HTTPS, SSH URL, and SCP remotes call git exactly once."""
    repository = FakeRepository()
    remote = FakeGitRemote()
    service = EvolutionTargetService(repository, remote)

    created = await service.create(_write(repo_url=repo_url), created_by=None)

    assert created.object_name == "deep-research"
    assert created.sub_dir == "skills/deep-research"
    assert created.default_ref == "main"
    assert remote.validated == [(repo_url, "main")]
    assert created.model_dump(by_alias=True)["repoUrl"] == repo_url


@pytest.mark.parametrize(
    ("body", "field", "reason"),
    [
        (
            _write(repo_url="http://git.example.com/agent-skills.git"),
            "repoUrl",
            "repo_url_format",
        ),
        (
            _write(repo_url="https://user:password@git.example.com/agent-skills.git"),
            "repoUrl",
            "repo_url_credentials",
        ),
        (
            _write(repo_url="ssh://user:password@git.example.com/agent-skills.git"),
            "repoUrl",
            "repo_url_credentials",
        ),
        (
            _write(repo_url="https://user@git.example.com/agent-skills.git"),
            "repoUrl",
            "repo_url_credentials",
        ),
        (
            _write(repo_url="https://git.example.com/agent-skills.git?token=secret"),
            "repoUrl",
            "repo_url_format",
        ),
        (
            _write(repo_url="https://git.example.com/agent-skills.git#branch"),
            "repoUrl",
            "repo_url_format",
        ),
        (
            _write(repo_url="https://[invalid/agent-skills.git"),
            "repoUrl",
            "repo_url_format",
        ),
        (
            _write(repo_url="ssh://git.example.com:not-a-port/agent-skills.git"),
            "repoUrl",
            "repo_url_format",
        ),
        (_write(repo_url="https:///missing-host.git"), "repoUrl", "repo_url_format"),
        (_write(sub_dir=""), "subDir", "sub_dir_format"),
        (_write(sub_dir="/absolute"), "subDir", "sub_dir_format"),
        (_write(sub_dir="skills/../secret"), "subDir", "sub_dir_format"),
        (_write(sub_dir=r"skills\\secret"), "subDir", "sub_dir_format"),
        (_write(default_ref="-main"), "defaultRef", "ref_format"),
        (_write(default_ref="feature..main"), "defaultRef", "ref_format"),
        (_write(default_ref="main."), "defaultRef", "ref_format"),
        (_write(default_ref="main/"), "defaultRef", "ref_format"),
        (_write(object_name="   "), "objectName", "object_name_invalid"),
        (_write(object_name="x" * 129), "objectName", "object_name_invalid"),
        (
            _write(object_name="bad\x01name"),
            "objectName",
            "object_name_invalid",
        ),
        (
            _write(repo_url="https://git.example.com/" + "a" * 1_024),
            "repoUrl",
            "repo_url_format",
        ),
        (_write(sub_dir="a" * 513), "subDir", "sub_dir_format"),
        (_write(default_ref="a" * 129), "defaultRef", "ref_format"),
    ],
)
async def test_invalid_local_target_input_returns_field_and_reason(
    body: EvolutionTargetWrite,
    field: str,
    reason: str,
) -> None:
    """Invalid URL, path, name, or ref fails before the remote or repository."""
    repository = FakeRepository()
    remote = FakeGitRemote()
    service = EvolutionTargetService(repository, remote)

    with pytest.raises(AppError) as raised:
        await service.create(body, created_by=None)

    assert raised.value.code == ErrorCode.REPO_INVALID
    assert raised.value.status_code == 422
    assert "password" not in raised.value.message
    assert "secret" not in raised.value.message
    assert raised.value.details == {"field": field, "reason": reason}
    assert remote.validated == []
    assert repository.rows == {}


async def test_create_duplicate_and_update_are_mapped_stably() -> None:
    """Duplicate create/rename and missing update use the public target errors."""
    repository = FakeRepository()
    remote = FakeGitRemote()
    service = EvolutionTargetService(repository, remote)
    first = await service.create(_write(), created_by=None)
    second = await service.create(
        _write(
            object_type="agent",
            object_name="general-purpose",
            repo_url="ssh://git@git.example.com/agents.git",
            sub_dir="agents/general-purpose",
        ),
        created_by=None,
    )

    with pytest.raises(AppError) as duplicate:
        await service.create(_write(), created_by=None)
    assert duplicate.value.code == ErrorCode.TARGET_EXISTS

    with pytest.raises(AppError) as rename:
        await service.update(
            second.id,
            _write(
                object_type="skill",
                object_name=first.object_name,
                repo_url="ssh://git@git.example.com/agents.git",
                sub_dir="agents/renamed",
            ),
        )
    assert rename.value.code == ErrorCode.TARGET_EXISTS

    with pytest.raises(AppError) as missing:
        await service.update("missing", _write())
    assert missing.value.code == ErrorCode.TARGET_NOT_FOUND

    updated = await service.update(
        second.id,
        _write(
            object_type="agent",
            object_name="general-purpose",
            repo_url="ssh://git@git.example.com/agents.git",
            sub_dir="agents/general-purpose-v2",
            enabled=False,
        ),
    )
    assert updated.id == second.id
    assert updated.sub_dir == "agents/general-purpose-v2"
    assert updated.enabled is False
    assert remote.validated[-1] == (
        "ssh://git@git.example.com/agents.git",
        "main",
    )


async def test_remote_failure_and_in_use_delete_are_sanitized() -> None:
    """Remote stderr-like text never reaches the API, and active runs block delete."""
    repository = FakeRepository()
    remote = FakeGitRemote(fail=True)
    service = EvolutionTargetService(repository, remote)

    with pytest.raises(AppError) as invalid:
        await service.create(_write(), created_by=None)
    assert invalid.value.code == ErrorCode.REPO_INVALID
    assert invalid.value.message == "repository or ref is invalid"
    assert "should-not-leak" not in invalid.value.message

    remote.fail = False
    created = await service.create(_write(), created_by=None)
    repository.active = True
    with pytest.raises(AppError) as in_use:
        await service.delete(created.id)
    assert in_use.value.code == ErrorCode.TARGET_IN_USE
    assert created.id in repository.rows


@pytest.mark.parametrize(
    ("failure", "field", "reason", "exit_code"),
    [
        (
            RepoInvalid(
                reason="ref_not_found",
                exit_code=2,
                stderr="fatal: couldn't find remote ref feature/missing",
            ),
            "defaultRef",
            "ref_not_found",
            2,
        ),
        (
            RepoInvalid(
                reason="repo_unreachable",
                exit_code=128,
                stderr=(
                    "fatal: unable to access "
                    "'https://bob:hunter2@git.example.com/org/repo.git/': "
                    "Could not resolve host\n"
                    "error: could not read /Users/alice/.ssh/id_rsa"
                ),
            ),
            "repoUrl",
            "repo_unreachable",
            128,
        ),
        (RepoInvalid(reason="git_timeout"), "repoUrl", "git_timeout", None),
        (RepoInvalid(reason="git_unavailable"), "repoUrl", "git_unavailable", None),
    ],
)
async def test_remote_failure_details_are_field_anchored_and_redacted(
    failure: RepoInvalid,
    field: str,
    reason: str,
    exit_code: int | None,
) -> None:
    """Administrator writes receive a field anchor and bounded git diagnostics."""
    repository = FakeRepository()
    remote = FakeGitRemote(fail=True, failure=failure)
    service = EvolutionTargetService(repository, remote)

    with pytest.raises(AppError) as raised:
        await service.create(_write(), created_by=None)

    details = raised.value.details
    assert details["field"] == field
    assert details["reason"] == reason
    command = details["command"]
    assert isinstance(command, Mapping)
    assert command["name"] == "git ls-remote"
    assert command.get("exitCode") == exit_code
    output = details.get("output", "")
    assert isinstance(output, str)
    assert "hunter2" not in output
    assert "should-not-leak" not in output
    assert "/Users/alice" not in output
    if failure.stderr:
        assert output
        assert len(output.encode()) <= 4_096
    else:
        assert output == ""
    assert raised.value.message == "repository or ref is invalid"


async def test_command_output_redaction_preserves_remote_paths() -> None:
    """Local absolute paths are removed while URL and ref paths stay readable."""
    output = redact_command_output(
        "\x1b[31mfatal\x1b[0m: unable to access "
        "'https://bob:hunter2@git.example.com/org/repo.git/': Could not resolve host\n"
        "error: could not read /Users/alice/.ssh/id_rsa\n"
        "error: bad config C:\\Users\\alice\\repo\\.git\\config\n"
        "token=abc123",
    )

    assert "hunter2" not in output
    assert "abc123" not in output
    assert "/Users/alice" not in output
    assert "C:\\Users\\alice" not in output
    assert "\x1b" not in output
    assert "git.example.com/org/repo.git" in output
    assert "Could not resolve host" in output
    assert output.count("<path>") >= 2


async def test_command_output_is_bounded_to_the_last_lines_and_bytes() -> None:
    """Diagnostics keep the tail and never exceed the line or byte budget."""
    lines = redact_command_output("\n".join(f"line {index}" for index in range(100)))
    kept = lines.splitlines()
    assert len(kept) == 40
    assert kept[0] == "line 60"
    assert kept[-1] == "line 99"

    huge = redact_command_output("start\n" + ("x" * 5_000))
    assert len(huge.encode()) <= 4_096
    assert huge.endswith("x")


async def test_delete_missing_and_versions_contract() -> None:
    """Missing targets use 404 and versions are sorted unique with the default ref."""
    repository = FakeRepository()
    remote = FakeGitRemote(tags=("v2.0.0", "v1.9.0", "v2.0.0"))
    service = EvolutionTargetService(repository, remote)
    created = await service.create(_write(), created_by=None)

    result = await service.versions(created.id)

    assert result.versions == ["v1.9.0", "v2.0.0"]
    assert result.default_ref == "main"
    assert remote.listed == [created.repo_url]
    await service.delete(created.id)
    assert created.id not in repository.rows

    with pytest.raises(AppError) as missing:
        await service.versions("missing")
    assert missing.value.code == ErrorCode.TARGET_NOT_FOUND

    with pytest.raises(AppError) as deleting:
        await service.delete("missing")
    assert deleting.value.code == ErrorCode.TARGET_NOT_FOUND


async def test_versions_remote_failure_is_sanitized() -> None:
    """Tag reads use the same stable invalid-remote response as saves."""
    repository = FakeRepository()
    remote = FakeGitRemote()
    service = EvolutionTargetService(repository, remote)
    created = await service.create(_write(), created_by=None)
    remote.fail = True

    with pytest.raises(AppError) as raised:
        await service.versions(created.id)

    assert raised.value.code == ErrorCode.REPO_INVALID
    assert raised.value.status_code == 422
    assert raised.value.message == "repository or ref is invalid"
    assert raised.value.details == {}
    assert "should-not-leak" not in raised.value.message


async def test_git_adapter_uses_argument_arrays_and_parses_tags() -> None:
    """The process boundary never invokes a shell and parses only tag refs."""
    calls: list[tuple[str, ...]] = []

    async def runner(argv: tuple[str, ...]) -> GitProcessResult:
        calls.append(argv)
        if "--tags" in argv:
            return GitProcessResult(
                returncode=0,
                stdout="a\trefs/tags/v2.0.0\nb\trefs/tags/v2.0.0^{}\nc\trefs/tags/v1.9.0\n",
                stderr="",
            )
        return GitProcessResult(returncode=0, stdout="sha\trefs/heads/main\n", stderr="")

    remote = SubprocessGitRemote(runner=runner, timeout_seconds=3)
    await remote.validate("https://git.example.com/repo.git", "main")
    tags = await remote.list_tags("https://git.example.com/repo.git")

    assert calls == [
        (
            "git",
            "ls-remote",
            "--exit-code",
            "--",
            "https://git.example.com/repo.git",
            "main",
        ),
        (
            "git",
            "ls-remote",
            "--tags",
            "--refs",
            "--",
            "https://git.example.com/repo.git",
        ),
    ]
    assert tags == ("v1.9.0", "v2.0.0")


@pytest.mark.parametrize(
    ("result", "reason", "exit_code"),
    [
        (
            GitProcessResult(returncode=2, stdout="", stderr="secret stderr"),
            "ref_not_found",
            2,
        ),
        (
            GitProcessResult(returncode=128, stdout="", stderr="token=secret"),
            "repo_unreachable",
            128,
        ),
        (TimeoutError("token=secret"), "git_timeout", None),
        (OSError("token=secret"), "git_unavailable", None),
    ],
)
async def test_git_adapter_failures_are_classified_without_leaking(
    result: GitProcessResult | BaseException,
    reason: str,
    exit_code: int | None,
) -> None:
    """Nonzero exits, timeouts, and OSError carry a reason and captured stderr."""
    argv_calls: list[tuple[str, ...]] = []

    async def runner(argv: tuple[str, ...]) -> GitProcessResult:
        argv_calls.append(argv)
        if isinstance(result, BaseException):
            raise result
        return result

    remote = SubprocessGitRemote(runner=runner, timeout_seconds=3)
    with pytest.raises(RepoInvalid) as raised:
        await remote.validate("https://git.example.com/repo.git", "main")

    assert str(raised.value) == "repository or ref is invalid"
    assert "secret" not in str(raised.value)
    assert raised.value.reason == reason
    assert raised.value.exit_code == exit_code
    assert "--exit-code" in argv_calls[0]


async def test_git_tag_listing_never_reports_a_missing_ref() -> None:
    """Exit code 2 while listing tags is an unreachable remote, not a bad ref."""

    async def runner(_argv: tuple[str, ...]) -> GitProcessResult:
        return GitProcessResult(returncode=2, stdout="", stderr="fatal: no access")

    remote = SubprocessGitRemote(runner=runner, timeout_seconds=3)
    with pytest.raises(RepoInvalid) as raised:
        await remote.list_tags("https://git.example.com/repo.git")

    assert raised.value.reason == "repo_unreachable"
    assert raised.value.exit_code == 2
    assert raised.value.stderr == "fatal: no access"


async def test_git_timeout_kills_and_reaps_the_child_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timed-out ls-remote cannot leave its child process running."""

    class BlockingProcess:
        """Child double that only exits when cancellation kills it."""

        returncode: int | None = None
        pid = 12345
        killed = False
        waited = False

        async def communicate(self) -> tuple[bytes, bytes]:
            """Block until the enclosing timeout cancels the operation."""
            await asyncio.sleep(60)
            return b"", b""

        def kill(self) -> None:
            """Record the kill and make wait resolve immediately."""
            self.killed = True
            self.returncode = -9

        async def wait(self) -> int:
            """Record that the killed child was reaped."""
            self.waited = True
            return -9

    process = BlockingProcess()
    calls: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    async def create_process(
        *argv: str,
        **kwargs: Any,
    ) -> BlockingProcess:
        calls.append((argv, kwargs))
        return process

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        create_process,
    )
    monkeypatch.setattr(
        os,
        "killpg",
        lambda pid, _signal: (
            process.kill() if pid == process.pid else pytest.fail(f"unexpected pid {pid}")
        ),
    )
    remote = SubprocessGitRemote(timeout_seconds=0.01)

    with pytest.raises(RepoInvalid):
        await remote.validate("https://git.example.com/repo.git", "main")

    assert calls[0][0] == (
        "git",
        "ls-remote",
        "--exit-code",
        "--",
        "https://git.example.com/repo.git",
        "main",
    )
    assert calls[0][1]["stdin"] is asyncio.subprocess.DEVNULL
    assert calls[0][1]["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert calls[0][1]["env"]["GCM_INTERACTIVE"] == "Never"
    assert calls[0][1]["start_new_session"] is True
    assert process.killed is True
    assert process.waited is True
