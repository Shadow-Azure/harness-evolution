"""Claude Code agent metadata facts shared by local import and parsing."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

CLAUDE_AGENT_META_KEYS = frozenset(
    {
        "agentType",
        "agentVersion",
        "agentListingDelta",
        "color",
        "description",
        "finished",
        "isBuiltIn",
        "model",
        "name",
        "parentAgentId",
        "parentToolUseId",
        "permissionMode",
        "pickedEffortModel",
        "planModeRequired",
        "promptSnapshot",
        "requestNonInteractive",
        "requestShape",
        "resolvedModel",
        "skillName",
        "skillVersion",
        "spawnDepth",
        "taskKind",
        "teamName",
        "toolUseId",
        "version",
        "workflowAgentId",
        "workflowId",
        "workflowToolUseId",
    },
)
MAX_UNKNOWN_META_FIELDS = 32
MAX_UNKNOWN_META_STRING = 256
_UNKNOWN_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,63}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MAX_INTEGER = 2**53


def unknown_metadata_fields(meta: Mapping[str, object]) -> tuple[str, ...]:
    """Return sorted safe keys that the known metadata schema does not own."""
    return tuple(
        sorted(
            key
            for key in meta
            if isinstance(key, str)
            and key not in CLAUDE_AGENT_META_KEYS
            and _UNKNOWN_KEY.fullmatch(key) is not None
        ),
    )


def sanitize_unknown_metadata(meta: Mapping[str, object]) -> dict[str, object]:
    """Keep bounded unknown scalar metadata without nested or provider bodies."""
    result: dict[str, object] = {}
    for key in unknown_metadata_fields(meta):
        value = _scalar(meta[key])
        if value is _DROP:
            continue
        result[key] = value
        if len(result) >= MAX_UNKNOWN_META_FIELDS:
            break
    return result


class _Drop:
    """Sentinel for an unknown value that is not a bounded scalar."""


_DROP = _Drop()


def _scalar(value: object) -> object:
    """Normalize one bounded scalar or ask the caller to drop it."""
    if isinstance(value, bool) or value is None:
        return _DROP if value is None else value
    if isinstance(value, int):
        return value if abs(value) <= _MAX_INTEGER else _DROP
    if isinstance(value, float):
        return value if math.isfinite(value) else _DROP
    if isinstance(value, str):
        cleaned = _CONTROL.sub("", value).strip()
        if not cleaned:
            return _DROP
        return cleaned[:MAX_UNKNOWN_META_STRING]
    return _DROP
