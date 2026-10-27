"""Shared Git failure disposition tests."""

from __future__ import annotations

import pytest

from app.service.evolution.git_failures import classify_git_failure
from app.third_party_api.git.workspace import GitOperationError


@pytest.mark.parametrize(
    ("stage", "retryable", "action", "blocked_stage", "error_stage"),
    [
        ("push", True, "blocked", "push", "push"),
        ("push", False, "blocked", "push", "push"),
        ("patch", True, "blocked", "patch", "patch"),
        ("commit", True, "blocked", "patch", "commit"),
        ("patch", False, "failed", None, "patch"),
        ("commit", False, "failed", None, "commit"),
        ("clone", True, "failed", None, "clone"),
        ("reference", False, "failed", None, "reference"),
    ],
)
def test_git_failure_disposition_is_centralized_by_stage_and_retryability(
    stage: str,
    retryable: bool,
    action: str,
    blocked_stage: str | None,
    error_stage: str,
) -> None:
    """Every caller receives one unambiguous blocked-or-failed disposition."""
    disposition = classify_git_failure(
        GitOperationError("safe failure", stage=stage, retryable=retryable),  # type: ignore[arg-type]
    )

    assert disposition.action == action
    assert disposition.blocked_stage == blocked_stage
    assert disposition.error_stage == error_stage
