"""Trace parser extension point with package-time parser discovery."""

from __future__ import annotations

import importlib
import pkgutil

from app.service.acquisition.parsers.base import (
    AgentLink,
    AgentMetaFacts,
    BaseTraceParser,
    ParseContext,
    ParsedBlock,
    ParsedEvent,
    ParsedIssue,
    ParsedTranscript,
    ParsedUserTurn,
    RootMetadata,
    SessionParseResult,
    TraceEvidence,
    TracePayload,
)
from app.service.acquisition.parsers.factory import (
    AmbiguousTraceRuntime,
    TraceParserFactory,
    UnsupportedTraceRuntime,
)

_INFRASTRUCTURE_MODULES = frozenset({"base", "factory"})


def _discover_parsers() -> None:
    """Import every sibling parser module so registration needs no factory edit."""
    for module in pkgutil.iter_modules(__path__):
        if module.name in _INFRASTRUCTURE_MODULES or module.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module.name}")


_discover_parsers()

__all__ = [
    "AgentLink",
    "AgentMetaFacts",
    "AmbiguousTraceRuntime",
    "BaseTraceParser",
    "ParseContext",
    "ParsedBlock",
    "ParsedEvent",
    "ParsedIssue",
    "ParsedTranscript",
    "ParsedUserTurn",
    "RootMetadata",
    "SessionParseResult",
    "TraceEvidence",
    "TraceParserFactory",
    "TracePayload",
    "UnsupportedTraceRuntime",
]
