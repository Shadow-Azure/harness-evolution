"""Managed Git host providers for authenticated push targets.

The workspace manager owns the provider-agnostic git execution flow. A
provider only answers the host-specific questions: what URL to push to, how a
git subprocess authenticates, and how to find or create a writable fork. New
hosts are added as subclasses plus one factory registry entry, so the
prepare/candidate/final state machine never learns a host-specific detail.
"""

from __future__ import annotations

import asyncio
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar
from urllib.parse import quote, urlsplit

import httpx
from pydantic import SecretStr

if TYPE_CHECKING:
    from app.config import Settings

GIT_ASKPASS_PATH = "/opt/harness/shared/git-askpass.sh"
"""Absolute askpass script path used when the deployment does not override it."""

_GITHUB_PUBLIC_HOST = "github.com"
_GITHUB_PUBLIC_API = "https://api.github.com"
_GITLAB_PUBLIC_HOST = "gitlab.com"
_SCP_REMOTE = re.compile(r"^(?P<user>[^@\s/]+)@(?P<host>[^:\s/]+):(?P<path>[^\s]+)$")
_FORK_POLL_ATTEMPTS = 6
_FORK_POLL_INTERVAL_SECONDS = 1.0


class GitPushProviderError(RuntimeError):
    """A sanitized provider failure safe to persist or display.

    Messages never contain the token, request headers, or a response body; the
    HTTP status is the only remote diagnostic retained.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        """Store one bounded message and an optional HTTP status."""
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class RemoteRepository:
    """Host, namespace, and name parsed from one credential-free repository URL."""

    scheme: str
    host: str
    port: int | None
    namespace: str
    name: str

    @property
    def host_and_port(self) -> str:
        """Return the host with the explicit port when one was configured."""
        return f"{self.host}:{self.port}" if self.port is not None else self.host

    @property
    def web_root(self) -> str:
        """Return the HTTPS web root used for pushed clone URLs."""
        scheme = "http" if self.scheme == "http" else "https"
        return f"{scheme}://{self.host_and_port}"


def parse_repository(repo_url: str) -> RemoteRepository:
    """Parse an HTTPS, SSH, or scp-like git remote without retaining credentials.

    A push always returns to the HTTPS web root: SSH ports are not reused for
    HTTPS, and a credential embedded in an SSH username is never copied.
    """
    normalized = repo_url.strip()
    scp = _SCP_REMOTE.fullmatch(normalized)
    if scp is not None:
        path = scp.group("path")
        return _repository_from_parts("https", scp.group("host"), None, path)
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https", "ssh"} or not parsed.hostname:
        raise GitPushProviderError("repository URL is not a supported git remote")
    try:
        port = parsed.port
    except ValueError:
        raise GitPushProviderError("repository URL has an invalid port") from None
    scheme = parsed.scheme
    if scheme == "ssh":
        port = None
    return _repository_from_parts(scheme, parsed.hostname, port, parsed.path)


def _repository_from_parts(
    scheme: str,
    host: str,
    port: int | None,
    raw_path: str,
) -> RemoteRepository:
    """Validate a parsed path and split it into namespace and project name."""
    path = raw_path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        raise GitPushProviderError("repository URL must include an owner and a repository")
    return RemoteRepository(
        scheme=scheme,
        host=host,
        port=port,
        namespace="/".join(parts[:-1]),
        name=parts[-1],
    )


type GitCommandRunner = Callable[
    [tuple[str, ...], Path | None],
    Awaitable["GitCommandResult"],
]


@dataclass(frozen=True, slots=True)
class GitCommandResult:
    """Minimal captured git output for provider template methods."""

    returncode: int
    stdout: str
    stderr: str


class GitPushProvider(ABC):
    """Unified push seam: URLs, credentials, fork discovery, and git execution."""

    provider_id: str
    git_username: str

    def __init__(
        self,
        *,
        token: SecretStr | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        askpass_path: str | None = None,
        fork_poll_attempts: int = _FORK_POLL_ATTEMPTS,
        fork_poll_interval_seconds: float = _FORK_POLL_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        """Bind the PAT and HTTP session without reading the environment per run."""
        self._token = token
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._askpass_path = askpass_path or os.environ.get("GIT_ASKPASS") or GIT_ASKPASS_PATH
        self._fork_poll_attempts = max(1, fork_poll_attempts)
        self._fork_poll_interval_seconds = max(0.0, fork_poll_interval_seconds)
        self._sleep = sleep or asyncio.sleep
        self._logins: dict[str, str] = {}

    @property
    def has_token(self) -> bool:
        """Return whether a PAT is available for fork discovery and push auth."""
        return self._token is not None and bool(self._token.get_secret_value())

    @abstractmethod
    def remote_url(
        self,
        repo_url: str,
        *,
        fork: bool = False,
        owner: str | None = None,
    ) -> str:
        """Return a credential-free HTTPS URL for the upstream or its fork."""

    def auth_environment(self) -> Mapping[str, str]:
        """Return git subprocess overrides; never log the returned mapping.

        The askpass script reads the username and PAT from the process
        environment, so a token never enters a remote URL or command argument.
        Without a PAT the ambient credential helper keeps working unchanged.
        """
        token = self._token
        if token is None or not token.get_secret_value():
            return {}
        return {
            "GIT_ASKPASS": self._askpass_path,
            "GIT_TERMINAL_PROMPT": "0",
            "HE_GIT_PUSH_USERNAME": self.git_username,
            "HE_GIT_PUSH_TOKEN": token.get_secret_value(),
        }

    @abstractmethod
    async def ensure_fork(self, upstream_url: str, owner: str | None = None) -> str:
        """Find or create a writable fork and return its credential-free URL."""

    @abstractmethod
    async def open_pull_request(
        self,
        fork_url: str,
        upstream_url: str,
        branch: str,
        title: str,
    ) -> str | None:
        """Return one pull-request URL when supported, otherwise ``None``."""

    async def remote_ref(
        self,
        runner: GitCommandRunner,
        workspace: Path,
        remote_url: str,
        ref: str,
    ) -> str | None:
        """Resolve one exact remote ref through the shared git execution seam."""
        result = await runner(
            ("git", "ls-remote", remote_url, ref),
            workspace,
        )
        if result.returncode != 0:
            raise GitPushProviderError("remote reference lookup failed")
        for line in result.stdout.splitlines():
            commit, separator, found = line.partition("\t")
            if separator and found == ref:
                return commit
        return None

    async def push_ref(
        self,
        runner: GitCommandRunner,
        workspace: Path,
        remote_url: str,
        refspec: str,
        *,
        force_with_lease: str | None = None,
    ) -> None:
        """Push one refspec without ever putting credentials in the URL."""
        argv: list[str] = ["git", "push"]
        if force_with_lease is not None:
            argv.append(f"--force-with-lease={force_with_lease}")
        argv.extend((remote_url, refspec))
        result = await runner(tuple(argv), workspace)
        if result.returncode != 0:
            raise GitPushProviderError("git push failed")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, object] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Send one API request and translate transport failures safely."""
        try:
            if self._client is not None:
                return await self._client.request(
                    method,
                    path,
                    headers=headers,
                    json=json,
                    params=params,
                )
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=False,
            ) as client:
                return await client.request(
                    method,
                    path,
                    headers=headers,
                    json=json,
                    params=params,
                )
        except httpx.HTTPError:
            raise GitPushProviderError("git host API request failed") from None

    async def _json_object(self, response: httpx.Response, failure: str) -> dict[str, object]:
        """Require a JSON object response without echoing its body."""
        if response.status_code >= 400:
            raise GitPushProviderError(failure, status_code=response.status_code)
        try:
            payload = response.json()
        except ValueError:
            raise GitPushProviderError(failure, status_code=response.status_code) from None
        if not isinstance(payload, dict):
            raise GitPushProviderError(failure, status_code=response.status_code)
        return payload

    async def _wait_for_fork(
        self,
        fetch: Callable[[], Awaitable[dict[str, object] | None]],
    ) -> None:
        """Poll a freshly created fork until the host reports it as ready."""
        for attempt in range(self._fork_poll_attempts):
            if await fetch() is not None:
                return
            if attempt + 1 < self._fork_poll_attempts:
                await self._sleep(self._fork_poll_interval_seconds)
        raise GitPushProviderError("git host did not expose the new fork in time")


class GitHubProvider(GitPushProvider):
    """GitHub.com and GitHub Enterprise push provider."""

    provider_id = "github"
    git_username = "x-access-token"

    def api_root(self, repo: RemoteRepository) -> str:
        """Derive the REST v3 root from the repository host."""
        if repo.host == _GITHUB_PUBLIC_HOST and repo.port is None:
            return _GITHUB_PUBLIC_API
        return f"{repo.web_root}/api/v3"

    def remote_url(
        self,
        repo_url: str,
        *,
        fork: bool = False,
        owner: str | None = None,
    ) -> str:
        """Return the canonical HTTPS push URL for GitHub."""
        repo = parse_repository(repo_url)
        target_owner = owner if owner is not None else repo.namespace
        if fork and owner is None:
            target_owner = self._require_login("fork owner is unknown", repo)
        return f"{repo.web_root}/{target_owner}/{repo.name}.git"

    async def ensure_fork(self, upstream_url: str, owner: str | None = None) -> str:
        """Find or create the authenticated user's fork of one GitHub repository."""
        repo = parse_repository(upstream_url)
        login = owner or await self.login(upstream_url)
        if repo.namespace == login:
            return self.remote_url(upstream_url)
        fork_url = self.remote_url(upstream_url, fork=True, owner=login)
        existing = await self._repo_exists(repo, owner=login)
        if existing:
            return fork_url
        response = await self._request(
            "POST",
            f"{self.api_root(repo)}/repos/{repo.namespace}/{repo.name}/forks",
            headers=self._headers(),
            json={"default_branch_only": False},
        )
        if response.status_code not in {202, 201, 200}:
            raise GitPushProviderError(
                "GitHub fork creation failed",
                status_code=response.status_code,
            )
        await self._wait_for_fork(lambda: self._repo_payload(repo, owner=login))
        return fork_url

    async def open_pull_request(
        self,
        fork_url: str,
        upstream_url: str,
        branch: str,
        title: str,
    ) -> str | None:
        """Automatic pull requests stay out of scope for this provider slice."""
        return None

    async def login(self, repo_url: str | None = None) -> str:
        """Resolve and cache the authenticated GitHub login for one host."""
        repo = parse_repository(repo_url or "https://github.com/placeholder/placeholder")
        cached = self._logins.get(repo.host_and_port)
        if cached is not None:
            return cached
        response = await self._request(
            "GET",
            f"{self.api_root(repo)}/user",
            headers=self._headers(),
        )
        payload = await self._json_object(response, "GitHub identity lookup failed")
        login = payload.get("login")
        if not isinstance(login, str) or not login.strip():
            raise GitPushProviderError("GitHub identity lookup returned no login")
        self._logins[repo.host_and_port] = login.strip()
        return self._logins[repo.host_and_port]

    def _require_login(self, failure: str, repo: RemoteRepository) -> str:
        """Return the cached login for this host or fail before building a URL."""
        login = self._logins.get(repo.host_and_port)
        if login is None:
            raise GitPushProviderError(failure)
        return login

    def _headers(self) -> Mapping[str, str]:
        """Return the GitHub authorization headers without exposing the token."""
        token = self._token
        if token is None or not token.get_secret_value():
            raise GitPushProviderError("GitHub push token is not configured")
        return {
            "Authorization": f"Bearer {token.get_secret_value()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _repo_exists(self, repo: RemoteRepository, *, owner: str) -> bool:
        """Return whether one fork repository already exists."""
        return await self._repo_payload(repo, owner=owner) is not None

    async def _repo_payload(
        self,
        repo: RemoteRepository,
        *,
        owner: str,
    ) -> dict[str, object] | None:
        """Fetch one repository, treating a 404 as an expected missing fork."""
        response = await self._request(
            "GET",
            f"{self.api_root(repo)}/repos/{owner}/{repo.name}",
            headers=self._headers(),
        )
        if response.status_code == 404:
            return None
        return await self._json_object(response, "GitHub fork lookup failed")


class GitLabProvider(GitPushProvider):
    """GitLab.com and self-managed GitLab push provider."""

    provider_id = "gitlab"
    git_username = "oauth2"

    def api_root(self, repo: RemoteRepository) -> str:
        """Derive the REST v4 root from the repository host."""
        return f"{repo.web_root}/api/v4"

    def remote_url(
        self,
        repo_url: str,
        *,
        fork: bool = False,
        owner: str | None = None,
    ) -> str:
        """Return the canonical HTTPS push URL for GitLab."""
        repo = parse_repository(repo_url)
        if not fork:
            return f"{repo.web_root}/{repo.namespace}/{repo.name}.git"
        target_owner = owner or self._require_login("fork owner is unknown", repo)
        return f"{repo.web_root}/{target_owner}/{repo.name}.git"

    async def ensure_fork(self, upstream_url: str, owner: str | None = None) -> str:
        """Find or create the authenticated user's fork of one GitLab project."""
        repo = parse_repository(upstream_url)
        login = owner or await self.login(upstream_url)
        if repo.namespace == login:
            return self.remote_url(upstream_url)
        fork_url = self.remote_url(upstream_url, fork=True, owner=login)
        if await self._project_payload(repo, fork_path=f"{login}/{repo.name}") is not None:
            return fork_url
        encoded = quote(f"{repo.namespace}/{repo.name}", safe="")
        response = await self._request(
            "POST",
            f"{self.api_root(repo)}/projects/{encoded}/fork",
            headers=self._headers(),
            json={"namespace_path": login},
        )
        if response.status_code not in {201, 200}:
            raise GitPushProviderError(
                "GitLab fork creation failed",
                status_code=response.status_code,
            )
        await self._wait_for_fork(
            lambda: self._project_payload(repo, fork_path=f"{login}/{repo.name}"),
        )
        return fork_url

    async def open_pull_request(
        self,
        fork_url: str,
        upstream_url: str,
        branch: str,
        title: str,
    ) -> str | None:
        """Automatic merge requests stay out of scope for this provider slice."""
        return None

    async def login(self, repo_url: str | None = None) -> str:
        """Resolve and cache the authenticated GitLab username for one host."""
        repo = parse_repository(repo_url or "https://gitlab.com/placeholder/placeholder")
        cached = self._logins.get(repo.host_and_port)
        if cached is not None:
            return cached
        response = await self._request(
            "GET",
            f"{self.api_root(repo)}/user",
            headers=self._headers(),
        )
        payload = await self._json_object(response, "GitLab identity lookup failed")
        username = payload.get("username")
        if not isinstance(username, str) or not username.strip():
            raise GitPushProviderError("GitLab identity lookup returned no username")
        self._logins[repo.host_and_port] = username.strip()
        return self._logins[repo.host_and_port]

    def _require_login(self, failure: str, repo: RemoteRepository) -> str:
        """Return the cached login for this host or fail before building a URL."""
        login = self._logins.get(repo.host_and_port)
        if login is None:
            raise GitPushProviderError(failure)
        return login

    def _headers(self) -> Mapping[str, str]:
        """Return the GitLab private-token header without exposing it in logs."""
        token = self._token
        if token is None or not token.get_secret_value():
            raise GitPushProviderError("GitLab push token is not configured")
        return {"PRIVATE-TOKEN": token.get_secret_value()}

    async def _project_payload(
        self,
        repo: RemoteRepository,
        *,
        fork_path: str,
    ) -> dict[str, object] | None:
        """Fetch one project by encoded full path, treating 404 as missing."""
        encoded = quote(fork_path, safe="")
        response = await self._request(
            "GET",
            f"{self.api_root(repo)}/projects/{encoded}",
            headers=self._headers(),
        )
        if response.status_code == 404:
            return None
        return await self._json_object(response, "GitLab fork lookup failed")


class GitPushProviderFactory:
    """Select one provider implementation from deployment configuration."""

    _registry: ClassVar[dict[str, type[GitPushProvider]]] = {
        "github": GitHubProvider,
        "gitlab": GitLabProvider,
    }

    @classmethod
    def create(
        cls,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> GitPushProvider:
        """Instantiate the configured provider; unknown values fail startup."""
        provider_id = settings.git_push_provider.strip().lower()
        implementation = cls._registry.get(provider_id)
        if implementation is None:
            raise ValueError(
                "HE_GIT_PUSH_PROVIDER must be one of: " + ", ".join(sorted(cls._registry)),
            )
        return implementation(token=settings.git_push_token, client=client)

    @classmethod
    def register(
        cls,
        provider_id: str,
        implementation: type[GitPushProvider],
    ) -> None:
        """Register a new host without touching any business service."""
        normalized = provider_id.strip().lower()
        if not normalized:
            raise ValueError("provider id must not be empty")
        cls._registry[normalized] = implementation

    @classmethod
    def registered(cls) -> Mapping[str, type[GitPushProvider]]:
        """Return a read-only view of the current registry for diagnostics."""
        return dict(cls._registry)


__all__ = [
    "GIT_ASKPASS_PATH",
    "GitCommandResult",
    "GitHubProvider",
    "GitLabProvider",
    "GitPushProvider",
    "GitPushProviderError",
    "GitPushProviderFactory",
    "RemoteRepository",
    "parse_repository",
]
