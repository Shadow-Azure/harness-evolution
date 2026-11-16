"""Session-source extension point with package-time adapter discovery."""

from __future__ import annotations

import importlib
import pkgutil

from app.third_party_api.session_source.base import (
    BaseSessionSourceAdapter,
    SessionInfo,
    SessionSourceEnvelope,
    SessionSourceSnapshot,
    SessionTrajectoryEnvelope,
)
from app.third_party_api.session_source.client import (
    HttpSessionSourceClient,
    SessionSourceFetcher,
)
from app.third_party_api.session_source.factory import SessionSourceFactory

_INFRASTRUCTURE_MODULES = frozenset({"base", "factory", "client"})


def _discover_adapters() -> None:
    """Import every sibling adapter module so registration needs no factory edit."""
    for module in pkgutil.iter_modules(__path__):
        if module.name in _INFRASTRUCTURE_MODULES or module.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module.name}")


_discover_adapters()

__all__ = [
    "BaseSessionSourceAdapter",
    "HttpSessionSourceClient",
    "SessionInfo",
    "SessionSourceEnvelope",
    "SessionSourceFactory",
    "SessionSourceFetcher",
    "SessionSourceSnapshot",
    "SessionTrajectoryEnvelope",
]
