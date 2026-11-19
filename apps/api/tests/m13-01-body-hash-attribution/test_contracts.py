"""OpenAPI contracts added by body-hash attribution and post-process anchors."""

from __future__ import annotations

from typing import Any, cast

from app.config import DatabaseDialect, Settings
from app.main import create_app


def _schemas() -> dict[str, Any]:
    """Return the generated component schemas for one SQLite app."""
    schema = create_app(Settings(db_dialect=DatabaseDialect.SQLITE)).openapi()
    return cast(dict[str, Any], schema["components"]["schemas"])


def test_bad_case_anchor_exposes_the_closed_kind_vocabulary() -> None:
    """anchor.kind is required and limited to event/node/post_process/unknown."""
    anchor = _schemas()["BadCaseAnchor"]
    assert anchor["required"] == ["agentId", "eventIndex", "kind"]
    assert anchor["properties"]["kind"]["enum"] == [
        "event",
        "node",
        "post_process",
        "unknown",
    ]
    assert anchor["properties"]["eventIndex"]["minimum"] == -1


def test_potential_row_exposes_anchor_source() -> None:
    """The wizard potential row carries the audited anchorSource."""
    row = _schemas()["PotentialPreviewItem"]
    assert "anchorSource" in row["required"]
    assert row["properties"]["anchorSource"]["enum"] == [
        "event",
        "node",
        "post_process",
        "unknown",
    ]


def test_run_target_exposes_the_resolved_revision() -> None:
    """The run card distinguishes the selected tag from its body-hash revision."""
    target = _schemas()["EvolutionRunTarget"]
    assert "targetRevision" in target["properties"]
    assert set(target["required"]) == {"type", "name", "version"}


def test_target_content_unresolved_is_a_stable_error_code() -> None:
    """The resolver failure is part of the public error vocabulary."""
    assert "TARGET_CONTENT_UNRESOLVED" in _schemas()["ErrorCode"]["enum"]
