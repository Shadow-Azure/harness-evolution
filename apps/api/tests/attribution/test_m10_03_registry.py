"""Engine registry fail-fast behavior."""

from __future__ import annotations

import pytest

from app.config import DatabaseDialect, Settings
from app.main import create_app
from app.service.evolution.attribution import (
    RuleBasedEngine,
    registered_engine_keys,
    resolve_attribution_engine,
)
from app.service.evolution.engine.contracts import ConfigError


def test_rule_v1_is_registered_and_resolved() -> None:
    """The only V2 engine resolves by its cache-key identity."""
    engine = resolve_attribution_engine("rule-v1")

    assert isinstance(engine, RuleBasedEngine)
    assert engine.key == "rule-v1"


def test_registered_keys_are_a_closed_stable_tuple() -> None:
    """New engines must be registered explicitly, not discovered dynamically."""
    assert registered_engine_keys() == ("rule-v1",)


@pytest.mark.parametrize("key", ["", "llm-v1", "rule-v2", "legacy-probe-import"])
def test_unknown_engine_key_fails_fast(key: str) -> None:
    """An unregistered key cannot silently produce an uncacheable probe."""
    with pytest.raises(ConfigError, match="unknown attribution engine"):
        resolve_attribution_engine(key)


def test_create_app_rejects_an_unregistered_configured_engine() -> None:
    """Startup fails before serving when HE_ATTRIBUTION_ENGINE is unknown."""
    with pytest.raises(ConfigError, match="unknown attribution engine"):
        create_app(
            Settings(
                db_dialect=DatabaseDialect.SQLITE,
                attribution_engine="llm-v1",
            ),
        )
