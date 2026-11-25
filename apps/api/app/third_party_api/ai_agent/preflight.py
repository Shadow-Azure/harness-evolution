"""Release check for the Skill runtime selected by the API's provider factory."""

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
    status = f"attribution.preflight provider={provider.provider_id}"
    status += f" bwrap_enabled={settings.attribution_bwrap_enabled}"
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
