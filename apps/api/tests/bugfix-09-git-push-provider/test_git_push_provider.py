"""Factory, URL, credential, and fork contracts for Git push providers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.third_party_api.git.provider import (
    GIT_ASKPASS_PATH,
    GitCommandResult,
    GitHubProvider,
    GitLabProvider,
    GitPushProvider,
    GitPushProviderError,
    GitPushProviderFactory,
    parse_repository,
)

TOKEN = "github_pat_placeholder_for_tests"


def settings(*, provider: str = "github", token: str | None = TOKEN) -> Settings:
    """Build minimal settings without reading a repository .env file."""
    return Settings(
        jwt_secret=SecretStr("provider-test-secret"),
        git_push_provider=cast(Any, provider),
        git_push_token=SecretStr(token) if token is not None else None,
    )


def client_for(
    handler: Callable[[httpx.Request], Awaitable[httpx.Response]],
    *,
    base_url: str = "https://api.github.com",
) -> httpx.AsyncClient:
    """Return a client whose transport is a deterministic async handler."""
    return httpx.AsyncClient(
        transport=httpx.MockTransport(cast(Any, handler)),
        base_url=base_url,
        timeout=1,
    )


def json_response(status: int, payload: object) -> httpx.Response:
    """Return one JSON response with a matching content type."""
    return httpx.Response(
        status,
        headers={"content-type": "application/json"},
        content=json.dumps(payload).encode(),
    )


def test_factory_selects_github_and_gitlab_by_configuration() -> None:
    """The registry turns one deployment setting into one implementation."""
    github = GitPushProviderFactory.create(settings(provider="github"))
    gitlab = GitPushProviderFactory.create(settings(provider="gitlab"))

    assert isinstance(github, GitHubProvider)
    assert isinstance(gitlab, GitLabProvider)
    assert github.has_token
    assert gitlab.auth_environment()["HE_GIT_PUSH_USERNAME"] == "oauth2"


def test_settings_keeps_the_push_token_secret_out_of_repr() -> None:
    """SecretStr keeps the PAT out of logs that render the settings object."""
    configured = settings()

    assert configured.git_push_token is not None
    assert configured.git_push_token.get_secret_value() == TOKEN
    assert TOKEN not in repr(configured)


def test_unknown_provider_fails_configuration_at_startup() -> None:
    """An unknown provider id is a startup failure, never a silent fallback."""
    with pytest.raises(ValidationError):
        settings(provider="gitea")


def test_factory_registry_accepts_a_new_subclass_without_business_changes() -> None:
    """A new host is one subclass plus one registry entry."""

    class FakeProvider(GitPushProvider):
        provider_id = "fake"
        git_username = "fake-user"

        def remote_url(
            self,
            repo_url: str,
            *,
            fork: bool = False,
            owner: str | None = None,
        ) -> str:
            return repo_url

        async def ensure_fork(self, upstream_url: str, owner: str | None = None) -> str:
            return upstream_url

        async def open_pull_request(
            self,
            fork_url: str,
            upstream_url: str,
            branch: str,
            title: str,
        ) -> str | None:
            return None

    GitPushProviderFactory.register("fake", FakeProvider)
    try:
        selected = GitPushProviderFactory.create(
            settings().model_copy(update={"git_push_provider": "fake"}),
        )
        assert isinstance(selected, FakeProvider)
        assert "fake" in GitPushProviderFactory.registered()
    finally:
        GitPushProviderFactory._registry.pop("fake", None)


def test_auth_environment_carries_askpass_inputs_but_never_a_url_token() -> None:
    """Credentials travel through env; remote URLs stay credential-free."""
    provider = GitHubProvider(
        token=SecretStr(TOKEN),
        askpass_path="/opt/harness/shared/test-askpass.sh",
    )
    environment = provider.auth_environment()

    assert environment["GIT_ASKPASS"] == "/opt/harness/shared/test-askpass.sh"
    assert environment["HE_GIT_PUSH_USERNAME"] == "x-access-token"
    assert environment["HE_GIT_PUSH_TOKEN"] == TOKEN
    assert TOKEN not in provider.remote_url("https://github.com/obra/superpowers.git")
    assert environment["GIT_ASKPASS"] != GIT_ASKPASS_PATH


def test_missing_token_keeps_the_ambient_credential_helper() -> None:
    """Without a PAT the repository still behaves like the old deployment."""
    provider = GitHubProvider(token=None)

    assert provider.auth_environment() == {}
    assert not provider.has_token


def test_https_ssh_and_scp_repository_urls_parse_only_the_git_identity() -> None:
    """Every accepted target remote becomes a credential-free host/path pair."""
    https = parse_repository("https://github.com/obra/superpowers.git")
    ssh = parse_repository("ssh://git@git.example.com:2222/group/skills/repo.git")
    scp = parse_repository("git@git.example.com:group/repo.git")

    assert (https.host, https.namespace, https.name) == (
        "github.com",
        "obra",
        "superpowers",
    )
    assert (ssh.host, ssh.port, ssh.namespace, ssh.name) == (
        "git.example.com",
        None,
        "group/skills",
        "repo",
    )
    assert (scp.host, scp.namespace, scp.name) == (
        "git.example.com",
        "group",
        "repo",
    )


def test_remote_urls_follow_provider_host_and_fork_owner() -> None:
    """GitHub and GitLab build the same shape while preserving their hosts."""
    github = GitHubProvider(token=SecretStr(TOKEN))
    gitlab = GitLabProvider(token=SecretStr(TOKEN))

    assert github.remote_url("https://github.com/obra/superpowers.git") == (
        "https://github.com/obra/superpowers.git"
    )
    assert (
        github.remote_url(
            "https://github.com/obra/superpowers.git",
            fork=True,
            owner="me",
        )
        == "https://github.com/me/superpowers.git"
    )
    assert (
        gitlab.remote_url(
            "https://gitlab.example.com/group/sub/repo.git",
            fork=True,
            owner="me",
        )
        == "https://gitlab.example.com/me/repo.git"
    )


async def test_github_ensure_fork_creates_then_polls_the_user_fork() -> None:
    """Fork creation is one POST followed by bounded readiness polling."""
    requests: list[tuple[str, str]] = []
    fork_created = False
    poll_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal fork_created, poll_count
        requests.append((request.method, str(request.url)))
        if request.url.path == "/user":
            return json_response(200, {"login": "me"})
        if request.url.path == "/repos/obra/superpowers":
            return json_response(404, {"message": "Not Found"})
        if request.method == "POST" and request.url.path.endswith("/forks"):
            assert request.headers["Authorization"] == f"Bearer {TOKEN}"
            assert json.loads(request.content) == {"default_branch_only": False}
            fork_created = True
            return json_response(202, {"full_name": "me/superpowers"})
        if request.url.path == "/repos/me/superpowers":
            if not fork_created:
                return json_response(404, {"message": "Not Found"})
            poll_count += 1
            if poll_count == 1:
                return json_response(404, {"message": "Not Found"})
            return json_response(200, {"full_name": "me/superpowers"})
        return json_response(500, {"message": "unexpected"})

    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)
        await asyncio.sleep(0)

    client = client_for(handler)
    provider = GitHubProvider(token=SecretStr(TOKEN), client=client, sleep=sleep)
    try:
        fork_url = await provider.ensure_fork(
            "https://github.com/obra/superpowers.git",
        )
    finally:
        await client.aclose()

    assert fork_url == "https://github.com/me/superpowers.git"
    assert ("POST", "https://api.github.com/repos/obra/superpowers/forks") in requests
    assert sleeps == [1.0]
    assert TOKEN not in fork_url


async def test_github_ensure_fork_skips_creation_when_repo_is_already_owned() -> None:
    """Pushing to the authenticated user's own repository needs no fork."""
    methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return json_response(200, {"login": "obra"})

    client = client_for(handler)
    provider = GitHubProvider(token=SecretStr(TOKEN), client=client)
    try:
        url = await provider.ensure_fork("https://github.com/obra/superpowers.git")
    finally:
        await client.aclose()

    assert url == "https://github.com/obra/superpowers.git"
    assert methods == ["GET"]


async def test_gitlab_self_hosted_fork_uses_encoded_v4_project_path() -> None:
    """Self-managed GitLab derives /api/v4 and forks into the user namespace."""
    posts: list[str] = []
    fork_reads = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal fork_reads
        if request.url.path == "/api/v4/user":
            assert request.headers["PRIVATE-TOKEN"] == TOKEN
            return json_response(200, {"username": "me"})
        if request.method == "POST" and request.url.path.endswith("/fork"):
            posts.append(request.url.path)
            assert json.loads(request.content) == {"namespace_path": "me"}
            return json_response(201, {"path_with_namespace": "me/repo"})
        if request.method == "GET" and request.url.path in {
            "/api/v4/projects/me/repo",
            "/api/v4/projects/me%2Frepo",
        }:
            fork_reads += 1
            if fork_reads == 1:
                return json_response(404, {"message": "404 Project Not Found"})
            return json_response(200, {"path_with_namespace": "me/repo"})
        if request.method == "GET" and "/projects/" in request.url.path:
            return json_response(404, {"message": "404 Project Not Found"})
        return json_response(500, {"message": "unexpected"})

    client = client_for(handler, base_url="https://gitlab.example.com")
    provider = GitLabProvider(token=SecretStr(TOKEN), client=client)
    try:
        fork_url = await provider.ensure_fork(
            "https://gitlab.example.com/group/sub/repo.git",
        )
    finally:
        await client.aclose()

    assert fork_url == "https://gitlab.example.com/me/repo.git"
    assert posts == ["/api/v4/projects/group/sub/repo/fork"]


async def test_provider_failure_is_sanitized_and_carries_only_the_status() -> None:
    """A rejected token never leaks into the persisted error message."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return json_response(401, {"message": f"bad token {TOKEN}"})

    client = client_for(handler)
    provider = GitHubProvider(token=SecretStr(TOKEN), client=client)
    try:
        with pytest.raises(GitPushProviderError) as raised:
            await provider.ensure_fork("https://github.com/obra/superpowers.git")
    finally:
        await client.aclose()

    assert raised.value.status_code == 401
    assert TOKEN not in str(raised.value)
    assert "bad token" not in str(raised.value)


async def test_template_git_methods_use_the_shared_runner(tmp_path: Path) -> None:
    """Common ref lookup and push stay provider-agnostic argument arrays."""
    calls: list[tuple[str, ...]] = []

    async def runner(
        argv: tuple[str, ...],
        _cwd: Path | None,
    ) -> GitCommandResult:
        calls.append(argv)
        if argv[1] == "ls-remote":
            return GitCommandResult(
                returncode=0,
                stdout="a" * 40 + "\trefs/heads/evo/20261121-run\n",
                stderr="",
            )
        return GitCommandResult(returncode=0, stdout="", stderr="")

    provider = GitHubProvider(token=SecretStr(TOKEN))
    ref = await provider.remote_ref(
        runner,
        tmp_path,
        "https://github.com/me/superpowers.git",
        "refs/heads/evo/20261121-run",
    )
    await provider.push_ref(
        runner,
        tmp_path,
        "https://github.com/me/superpowers.git",
        "a" * 40 + ":refs/heads/evo/20261121-run",
    )

    assert ref == "a" * 40
    assert calls == [
        (
            "git",
            "ls-remote",
            "https://github.com/me/superpowers.git",
            "refs/heads/evo/20261121-run",
        ),
        (
            "git",
            "push",
            "https://github.com/me/superpowers.git",
            "a" * 40 + ":refs/heads/evo/20261121-run",
        ),
    ]
    assert TOKEN not in " ".join(" ".join(call) for call in calls)
