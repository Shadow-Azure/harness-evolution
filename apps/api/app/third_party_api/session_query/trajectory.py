"""Canonical NDJSON trajectory parsing shared by upstream session clients."""

from __future__ import annotations

import json
from typing import Any

from app.third_party_api.session_query.models import SessionTrajectory

MAX_TRAJECTORY_BYTES = 64 * 1024 * 1024
MAX_TRAJECTORY_LINE_BYTES = 1024 * 1024
MAX_TRAJECTORY_LINES = 1_000_000


class DuplicateJsonKeyError(ValueError):
    """Reject ambiguous JSON objects returned by an upstream service."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError
        result[key] = value
    return result


class TrajectoryFormatError(ValueError):
    """One canonical trajectory rejected for an upstream-safe reason."""

    def __init__(self, message: str, *, empty: bool = False) -> None:
        """Carry the sanitized message and whether the body had no lines."""
        super().__init__(message)
        self.message = message
        self.empty = empty


def canonicalize_ndjson(text: str) -> SessionTrajectory:
    """Return the canonical trajectory for one NDJSON response body.

    Split on ``\\n`` instead of ``splitlines`` so U+2028/U+2029 inside a legal
    JSON string are not treated as frame separators. Every non-empty line must
    be one JSON object; lines are re-serialized with stable separators.
    """
    if len(text.encode("utf-8")) > MAX_TRAJECTORY_BYTES:
        raise TrajectoryFormatError("trajectory response exceeded the size limit")
    lines = [line.rstrip("\r") for line in text.split("\n") if line.strip()]
    if not lines:
        raise TrajectoryFormatError(
            "session query service returned an empty trajectory",
            empty=True,
        )
    if len(lines) > MAX_TRAJECTORY_LINES:
        raise TrajectoryFormatError("trajectory response exceeded the line limit")
    canonical: list[str] = []
    for line in lines:
        if len(line.encode("utf-8")) > MAX_TRAJECTORY_LINE_BYTES:
            raise TrajectoryFormatError("trajectory line exceeded the size limit")
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except (json.JSONDecodeError, DuplicateJsonKeyError) as exc:
            raise TrajectoryFormatError("trajectory line was not JSON") from exc
        if not isinstance(value, dict):
            raise TrajectoryFormatError("trajectory line was not a JSON object")
        canonical.append(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        )
    return SessionTrajectory(content="\n".join(canonical), line_count=len(canonical))


def canonicalize_body(body: bytes) -> SessionTrajectory:
    """Decode one UTF-8 NDJSON body and return its canonical trajectory."""
    if len(body) > MAX_TRAJECTORY_BYTES:
        raise TrajectoryFormatError("trajectory response exceeded the size limit")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrajectoryFormatError("trajectory response was not UTF-8") from exc
    return canonicalize_ndjson(text)
