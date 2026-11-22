"""Run the real app with deterministic remote git validation for browser smoke."""

from __future__ import annotations

import os

import uvicorn

from app.config import Settings
from app.main import create_app
from tests.target_content_support import FakeDefinitionSource
from app.third_party_api.git.remote import RepoInvalid


class DeterministicGitRemote:
    """Validate test remotes without external network access."""

    async def validate(self, repo_url: str, ref: str) -> None:
        if "invalid.example.com" in repo_url:
            raise RepoInvalid(
                reason="repo_unreachable",
                exit_code=128,
                stderr=(
                    "fatal: unable to access "
                    "'https://invalid.example.com/repo.git/': Could not resolve host\n"
                    "error: could not read /Users/e2e/private-key"
                ),
            )
        if ref == "bad-ref":
            raise RepoInvalid(
                reason="ref_not_found",
                exit_code=2,
                stderr="fatal: couldn't find remote ref bad-ref",
            )

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        if "invalid.example.com" in repo_url:
            raise RepoInvalid(
                reason="repo_unreachable",
                exit_code=128,
                stderr="fatal: unable to access: Could not resolve host",
            )
        return ("v2.0.0", "v1.9.0")


def main() -> None:
    """Serve the composed application on the requested loopback port."""
    app = create_app(Settings(), git_remote=DeterministicGitRemote(), definition_source=FakeDefinitionSource())
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ["HE_PORT"]),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
