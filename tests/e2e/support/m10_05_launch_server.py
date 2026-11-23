"""Run the real app with deterministic remote git validation for the m10-05 smoke."""

from __future__ import annotations

import os

import uvicorn

from app.config import Settings
from app.main import create_app
from m5_launch_server import DeterministicGitRemote


def main() -> None:
    """Serve the composed application on the requested loopback port."""
    if os.environ.get("AI_AGENT_PROVIDER") == "script-test":
        from app.third_party_api.ai_agent import register_provider
        from tests.attribution.test_local_runtime import ScriptAgent

        register_provider(ScriptAgent.provider_id, ScriptAgent)
    settings = Settings()
    app = create_app(settings, git_remote=DeterministicGitRemote())
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ["HE_PORT"]),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
