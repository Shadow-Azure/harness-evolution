"""Run the real app with deterministic remote git validation for the launch-wizard smoke."""

from __future__ import annotations

import os

import uvicorn

from app.config import Settings
from app.main import create_app
from app.third_party_api.git.remote import RepoInvalid


class DeterministicGitRemote:
    """Validate test remotes without external network access."""

    async def validate(self, repo_url: str, ref: str) -> None:
        """Accept every test remote except the reserved invalid host."""
        if "invalid.example.com" in repo_url or ref == "bad-ref":
            raise RepoInvalid("invalid test remote")

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Return deterministic tags so the wizard version dropdown is stable."""
        if "invalid.example.com" in repo_url:
            raise RepoInvalid("invalid test remote")
        return ("synthetic-1", "v2.0.0", "v1.9.0")


def main() -> None:
    """Serve the composed application on the requested loopback port."""
    app = create_app(Settings(), git_remote=DeterministicGitRemote())
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ["HE_PORT"]),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
