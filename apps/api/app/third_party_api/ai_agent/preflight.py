"""Release check for the Skill runtime selected by the API's provider factory."""

import sys

from app.config import Settings
from app.third_party_api.ai_agent.base import SKILL_UNSUPPORTED
from app.third_party_api.ai_agent.factory import build_agent_provider


def main() -> int:
    try:
        provider = build_agent_provider(Settings())
    except ValueError:
        # A settings validation error can contain environment values.
        print("attribution.preflight error_code=ATTRIBUTION_CONFIG_INVALID", file=sys.stderr)
        return 1
    reason = provider.skill_preflight_error()
    if reason == SKILL_UNSUPPORTED:
        print(f"attribution.preflight provider={provider.provider_id} cache_only=True")
        return 0
    if reason:
        print(
            f"attribution.preflight provider={provider.provider_id} error_code={reason}",
            file=sys.stderr,
        )
        return 1
    print(f"attribution.preflight provider={provider.provider_id} ready=True")
    return 0


if __name__ == "__main__":
    sys.exit(main())
