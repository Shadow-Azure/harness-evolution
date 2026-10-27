"""Run-detail service projection for the six-step UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.db.models.evolution import EvolutionRunRecord, EvolutionRunSummaryRecord
from app.service.evolution.runs import EvolutionRunService

NOW = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)


def _run(*, status: str = "running", progress_unit: int = 4) -> EvolutionRunRecord:
    """Build one complete run row backed by real workspace fields."""
    return EvolutionRunRecord(
        id="run-detail",
        title="deep-research self evolution",
        mode="full",
        engine_key="full",
        eval_config={},
        target_config_id=None,
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        repo_url="https://example.invalid/skills.git",
        sub_dir="skills/deep-research",
        repo_path="data/repos/target",
        base_ref="v2.0.0",
        base_commit="9f3c2a1",
        branch_name="evo/run-detail",
        workspace_path="data/workspaces/run-detail",
        remote_name="origin",
        push_status="succeeded",
        pushed_at=NOW,
        push_error=None,
        window_from=date(2026, 8, 20),
        window_to=date(2026, 9, 10),
        models=["glm-5.3"],
        status=status,
        blocked_stage="eval" if status == "blocked" else None,
        retry_attempts=2,
        next_retry_at=NOW,
        eval_status="failed" if status == "blocked" else "pending",
        error_stage="eval" if status == "blocked" else None,
        error_message="sandbox timeout" if status == "blocked" else None,
        error_at=NOW if status == "blocked" else None,
        progress_unit=progress_unit,
        stats={
            "sessions": 4,
            "probes": 3,
            "byAttributeType": {
                "model": 1,
                "prompt": 1,
                "error": 1,
                "nonIssue": 0,
            },
        },
        created_by="user-1",
        created_at=NOW,
        finished_at=None,
    )


@dataclass
class FakeRunStore:
    """Return one summary and its workspace-bearing run row."""

    summary: EvolutionRunSummaryRecord

    async def list_summaries(self) -> tuple[EvolutionRunSummaryRecord, ...]:
        """Return the deterministic summary tuple."""
        return (self.summary,)

    async def get_summary(self, run_id: str) -> EvolutionRunSummaryRecord | None:
        """Return the deterministic summary when its id matches."""
        return self.summary if self.summary.run.id == run_id else None


async def test_detail_returns_workspace_and_backend_owned_step_states() -> None:
    """The detail shell carries all six states without frontend inference."""
    summary = EvolutionRunSummaryRecord(
        run=_run(),
        cluster_count=2,
        accepted_count=0,
        final=None,
        created_by_name="Ada",
    )

    detail = await EvolutionRunService(FakeRunStore(summary)).detail("run-detail")

    assert detail is not None
    assert detail.workspace.branch_name == "evo/run-detail"
    assert detail.workspace.base_ref == "v2.0.0"
    assert detail.workspace.repo_path == "data/repos/target"
    assert [step.key for step in detail.steps] == [
        "input",
        "clusters",
        "attribution",
        "severity",
        "iteration",
        "final",
    ]
    assert [step.status for step in detail.steps] == [
        "done",
        "done",
        "done",
        "done",
        "active",
        "pending",
    ]
    assert detail.steps[4].detail == "第 1/2 轮"
    assert detail.steps[5].clickable is False
    assert detail.last_event_seq == 0


async def test_detail_reports_blocked_retry_and_evaluation_context() -> None:
    """Blocked runs expose their sanitized stage, retries, and next retry time."""
    summary = EvolutionRunSummaryRecord(
        run=_run(status="blocked", progress_unit=4),
        cluster_count=1,
        accepted_count=0,
        final=None,
        created_by_name="Ada",
    )

    detail = await EvolutionRunService(FakeRunStore(summary)).detail("run-detail")

    assert detail is not None
    assert detail.blocked_stage == "eval"
    assert detail.retry_attempts == 2
    assert detail.next_retry_at == NOW
    assert detail.eval_status == "failed"
    assert detail.error is not None
    assert detail.error.message == "sandbox timeout"
