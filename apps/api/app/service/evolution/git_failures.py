"""Central Git failure disposition shared by evolution orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.service.evolution.engine.contracts import EvolutionBlockedStage
from app.third_party_api.git.workspace import GitOperationError, GitStage

GitFailureAction = Literal["blocked", "failed"]


@dataclass(frozen=True, slots=True)
class GitFailureDisposition:
    """One safe blocked-or-failed decision for a Git operation failure."""

    action: GitFailureAction
    blocked_stage: EvolutionBlockedStage | None
    error_stage: GitStage


def classify_git_failure(error: GitOperationError) -> GitFailureDisposition:
    """Classify publication, retryable patch/commit, and terminal failures once."""
    if error.stage == "push":
        return GitFailureDisposition(
            action="blocked",
            blocked_stage="push",
            error_stage="push",
        )
    if error.stage in {"patch", "commit"} and error.retryable:
        return GitFailureDisposition(
            action="blocked",
            blocked_stage="patch",
            error_stage=error.stage,
        )
    return GitFailureDisposition(
        action="failed",
        blocked_stage=None,
        error_stage=error.stage,
    )
