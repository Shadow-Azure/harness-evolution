"""Bad-case sync-source extension point with package-time provider discovery."""

from __future__ import annotations

import importlib
import pkgutil

from app.third_party_api.bad_case_sync_source.base import BaseBadCaseSyncSource
from app.third_party_api.bad_case_sync_source.factory import (
    PROVIDER_ENV,
    BadCaseSyncSourceFactory,
)

_INFRASTRUCTURE_MODULES = frozenset({"base", "factory"})


def _discover_sources() -> None:
    """Import every sibling provider module so registration needs no factory edit."""
    for module in pkgutil.iter_modules(__path__):
        if module.name in _INFRASTRUCTURE_MODULES or module.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module.name}")


_discover_sources()

__all__ = [
    "PROVIDER_ENV",
    "BadCaseSyncSourceFactory",
    "BaseBadCaseSyncSource",
]
