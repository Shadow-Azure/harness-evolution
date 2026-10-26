"""Target validation, service orchestration, and Git remote adapter contracts."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution_targets import (
    EvolutionTargetConflict,
    EvolutionTargetRecord,
)
from app.errors import AppError, ErrorCode
from app.main import create_app
from app.service.evolution.targets import (
    EvolutionTargetService,
    EvolutionTargetWrite,
)
from app.third_party_api.git.remote import (
    GitProcessResult,
    RepoInvalid,
    SubprocessGitRemote,
)

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

    async def list(self, *, enabled_only: bool = False) -> tuple[EvolutionTargetRecord, ...]:
        """Return rows using the production order."""
        rows = sorted(
            self.rows.values(),
            key=lambda row: (row.object_type, row.object_name, row.id),
        )
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return tuple(rows)

    async def get(self, target_id: str) -> EvolutionTargetRecord | None:
        """Return one stored row."""
        return self.rows.get(target_id)

    async def find(
        self,
        object_type: str,
        object_name: str,
    ) -> EvolutionTargetRecord | None:
        """Find a row by the unique object pair."""
        return next(
            (
                row
                for row in self.rows.values()
                if row.object_type == object_type and row.object_name == object_name
            ),
            None,
        )

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
    ) -> EvolutionTargetRecord:
        """Replace editable fields or raise the production missing/conflict errors."""
        if target_id not in self.rows:
            raise LookupError("missing")
        existing = await self.find(str(values["object_type"]), str(values["object_name"]))
        if existing is not None and existing.id != target_id:
            raise EvolutionTargetConflict
        row = _record(target_id, values)
        self.rows[target_id] = row
        return row

    async def delete(self, target_id: str) -> bool:
        """Delete and report whether the row existed."""
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
        enabled=bool(values["enabled"]),
    )


def _write(**overrides: Any) -> EvolutionTargetWrite:
    """Build a valid request with targeted overrides."""
    values: dict[str, Any] = {
        "object_type": "skill",
        "object_name": " deep-research ",
        "repo_url": "https://git.example.com/agent-skills.git",
        "sub_dir": " skills/deep-research ",
        "default_ref": " main ",
        "enabled": True,
    }
    values.update(overrides)
    return EvolutionTargetWrite(**values)


class FakeGitRemote:
    """Record remote calls and return configured tags."""

    def __init__(self, *, fail: bool = False, tags: tuple[str, ...] = ("v2.0.0", "v1.9.0")) -> None:
        """Configure behavior for one service test."""
        self.fail = fail
        self.tags = tags
        self.validated: list[tuple[str, str]] = []
        self.listed: list[str] = []

    async def validate(self, repo_url: str, ref: str) -> None:
        """Record validation or raise a sanitized remote failure."""
        self.validated.append((repo_url, ref))
        if self.fail:
            raise RepoInvalid("token=should-not-leak")

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Record tag listing or raise a sanitized remote failure."""
        self.listed.append(repo_url)
        if self.fail:
            raise RepoInvalid("token=should-not-leak")
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
async def target_http(tmp_path: Path) -> AsyncIterator[TargetHttpEnvironment]:
    """Provide member/admin clients over one application with a fake git remote."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("target-http-signing-secret-with-sufficient-length"),
        admin_username="admin",
        admin_password=SecretStr(TARGET_ADMIN_TEMP_PASSWORD),
    )
    remote = FakeGitRemote(tags=("v2.0.0", "v1.9.0"))
    app = create_app(settings, git_remote=remote)
    transport = httpx.ASGITransport(app=app)
    admin = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    member = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    try:
        async with app.router.lifespan_context(app):
            await app.state.identity.create_user(
                username="member",
                display_name="Member",
                password=TARGET_MEMBER_TEMP_PASSWORD,
                role="member",
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

    missing = await target_http.admin.delete("/api/evolution/targets/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TARGET_NOT_FOUND"


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
    "body",
    [
        _write(repo_url="http://git.example.com/agent-skills.git"),
        _write(repo_url="https://user:password@git.example.com/agent-skills.git"),
        _write(repo_url="ssh://user:password@git.example.com/agent-skills.git"),
        _write(repo_url="https://git.example.com/agent-skills.git?token=secret"),
        _write(repo_url="https://git.example.com/agent-skills.git#branch"),
        _write(repo_url="https://[invalid/agent-skills.git"),
        _write(repo_url="ssh://git.example.com:not-a-port/agent-skills.git"),
        _write(repo_url="https:///missing-host.git"),
        _write(sub_dir=""),
        _write(sub_dir="/absolute"),
        _write(sub_dir="skills/../secret"),
        _write(sub_dir=r"skills\\secret"),
        _write(default_ref="-main"),
        _write(object_name="   "),
    ],
)
async def test_invalid_local_target_input_returns_sanitized_repo_invalid(
    body: EvolutionTargetWrite,
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
    "result",
    [
        GitProcessResult(returncode=2, stdout="", stderr="secret stderr"),
        GitProcessResult(returncode=128, stdout="", stderr="token=secret"),
        TimeoutError("token=secret"),
    ],
)
async def test_git_adapter_failures_are_sanitized(
    result: GitProcessResult | BaseException,
) -> None:
    """Nonzero exits and timeouts collapse into one generic RepoInvalid."""

    async def runner(_argv: tuple[str, ...]) -> GitProcessResult:
        if isinstance(result, BaseException):
            raise result
        return result

    remote = SubprocessGitRemote(runner=runner, timeout_seconds=3)
    with pytest.raises(RepoInvalid) as raised:
        await remote.validate("https://git.example.com/repo.git", "main")

    assert str(raised.value) == "repository or ref is invalid"
    assert "secret" not in str(raised.value)


async def test_git_timeout_kills_and_reaps_the_child_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timed-out ls-remote cannot leave its child process running."""

    class BlockingProcess:
        """Child double that only exits when cancellation kills it."""

        returncode: int | None = None
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
    assert process.killed is True
    assert process.waited is True
