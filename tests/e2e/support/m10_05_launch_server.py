"""Run the real app with deterministic remote git validation for the m10-05 smoke."""

from __future__ import annotations

import os

import uvicorn

from app.config import Settings
from app.main import create_app
from m5_launch_server import DeterministicGitRemote


def main() -> None:
    """Serve the composed application on the requested loopback port."""
    settings = Settings()
    if settings.attribution_agent == "e2e-script":
        from app.third_party_api.attribution.backend import AgentFactory
        from tests.attribution.test_local_runtime import ScriptAgent

        AgentFactory.providers["e2e-script"] = ScriptAgent
    app = create_app(settings, git_remote=DeterministicGitRemote())
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ["HE_PORT"]),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
