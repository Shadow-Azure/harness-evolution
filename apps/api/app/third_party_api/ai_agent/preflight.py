"""Release check for the Skill runtime selected by the API's provider factory."""

import asyncio
import sys

from app.config import Settings
from app.third_party_api.ai_agent.base import SKILL_UNSUPPORTED
from app.third_party_api.ai_agent.factory import build_agent_provider


def main() -> int:
    try:
        settings = Settings()
        provider = build_agent_provider(settings)
    except ValueError:
        # A settings validation error can contain environment values.
        print("attribution.preflight error_code=ATTRIBUTION_CONFIG_INVALID", file=sys.stderr)
        return 1
    # The capability line enumerates the explicit provider protocol: declared
    # skills, structured credential state, and binary usability. ``unknown``
    # auth means the probe never reached a working deployment, which is also
    # when the configured binary counts as missing.
    health = asyncio.run(provider.health_check())
    binary = "missing" if health.auth == "unknown" else "present"
    status = (
        f"attribution.preflight provider={provider.provider_id}"
        f" skills={'yes' if provider.supports_skills else 'no'}"
        f" auth={health.auth} bin={binary}"
        f" bwrap_enabled={settings.attribution_bwrap_enabled}"
    )
    reason = provider.skill_preflight_error()
    if reason == SKILL_UNSUPPORTED:
        print(f"{status} cache_only=True")
        return 0
    if reason:
        print(f"{status} error_code={reason}", file=sys.stderr)
        return 1
    print(f"{status} ready=True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
