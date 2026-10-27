"""Run-list service grouping, progress, and public-card projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest

from app.db.models.evolution import (
    EvolutionFinalRecord,
    EvolutionRunRecord,
    EvolutionRunSummaryRecord,
)
from app.service.evolution.runs import EvolutionRunService

NOW = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)


def _run(
    run_id: str,
    status: str,
    *,
    progress_unit: int = 0,
    stats: dict[str, object] | None = None,
    error: tuple[str, str] | None = None,
) -> EvolutionRunRecord:
    """Build a complete run snapshot for a deterministic service test."""
    return EvolutionRunRecord(
        id=run_id,
        title=f"{run_id} title",
        mode="full",
        engine_key="full",
        eval_config={},
        target_config_id=None,
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        repo_url="https://example.invalid/skills.git",
        sub_dir="skills/deep-research",
        repo_path=None,
        base_ref="v2.0.0",
        base_commit=None,
        branch_name=f"evo/{run_id}",
        workspace_path=None,
        remote_name="origin",
        push_status="succeeded",
        pushed_at=NOW,
        push_error=None,
        window_from=date(2026, 8, 20),
        window_to=date(2026, 9, 10),
        models=["glm-5.3"],
        status=status,
        blocked_stage="eval" if status == "blocked" else None,
        retry_attempts=0,
        next_retry_at=None,
        eval_status="pending",
        error_stage=error[0] if error else None,
        error_message=error[1] if error else None,
        error_at=NOW if error else None,
        progress_unit=progress_unit,
        stats=stats or {},
        created_by="user-1",
        created_at=NOW,
        finished_at=NOW if status in {"completed", "failed", "interrupted"} else None,
    )


def _summary(
    run: EvolutionRunRecord,
    *,
    clusters: int = 0,
    accepted: int = 0,
    final: EvolutionFinalRecord | None = None,
    creator: str | None = "Ada",
) -> EvolutionRunSummaryRecord:
    """Build the repository projection consumed by the run service."""
    return EvolutionRunSummaryRecord(
        run=run,
        cluster_count=clusters,
        accepted_count=accepted,
        final=final,
        created_by_name=creator,
    )


@dataclass
class FakeRunStore:
    """Return summaries in the exact repository order."""

    rows: tuple[EvolutionRunSummaryRecord, ...]

    async def list_summaries(self) -> tuple[EvolutionRunSummaryRecord, ...]:
        """Return the preordered summaries."""
        return self.rows

    async def get_summary(self, run_id: str) -> EvolutionRunSummaryRecord | None:
        """Return one preordered summary by run id."""
        return next((row for row in self.rows if row.run.id == run_id), None)


async def test_run_list_groups_by_status_without_reordering_repository_rows() -> None:
    """Working states stay in running and terminal states stay in history."""
    rows = (
        _summary(_run("preparing", "preparing")),
        _summary(_run("running", "running")),
        _summary(_run("blocked", "blocked")),
        _summary(_run("completed", "completed")),
        _summary(_run("failed", "failed", error=("eval", "sandbox timeout"))),
        _summary(_run("interrupted", "interrupted", error=("push", "network lost"))),
    )

    result = await EvolutionRunService(FakeRunStore(rows)).list()

    assert [item.run_id for item in result.running] == [
        "preparing",
        "running",
        "blocked",
    ]
    assert [item.run_id for item in result.history] == [
        "completed",
        "failed",
        "interrupted",
    ]


@pytest.mark.parametrize(
    ("unit", "label", "done_rounds", "percent"),
    [
        (0, "第 1/6 步 · 筛选输入中…", 0, 0),
        (1, "第 2/6 步 · 问题聚类中…", 0, 14),
        (2, "第 3/6 步 · LLM 归因置信度中…", 0, 29),
        (3, "第 4/6 步 · 严重程度排序中…", 0, 43),
        (4, "第 5/6 步 · 迭代优化 · 第 1/2 轮", 0, 57),
        (5, "第 5/6 步 · 迭代优化 · 第 2/2 轮", 1, 71),
        (6, "第 6/6 步 · 测试集终评中…", 2, 86),
        (7, "第 6/6 步 · 测试集终评中…", 2, 100),
    ],
)
async def test_progress_copy_and_percent_are_backend_owned(
    unit: int,
    label: str,
    done_rounds: int,
    percent: int,
) -> None:
    """Every displayed progress value comes from the service projection."""
    run = _run("run-progress", "running", progress_unit=unit)
    service = EvolutionRunService(FakeRunStore((_summary(run, clusters=2, accepted=1),)))

    card = (await service.list()).running[0]

    assert card.progress.unit == unit
    assert card.progress.total == 7
    assert card.progress.percent == percent
    assert card.progress.stage_label == label
    assert card.progress.done_rounds == done_rounds
    assert card.progress.accepted == 1


async def test_progress_percent_rounds_half_up() -> None:
    """A fractional percentage rounds up rather than using Python bankers rounding."""
    run = _run("run-half", "running", progress_unit=1)
    service = EvolutionRunService(FakeRunStore((_summary(run, clusters=3),)))

    card = (await service.list()).running[0]

    assert card.progress.total == 8
    assert card.progress.percent == 13


async def test_final_error_stats_and_creator_are_projected_for_the_card() -> None:
    """History keeps final and error facts while normalization fills absent stats."""
    final = EvolutionFinalRecord(
        run_id="run-final",
        best_version="v2.0.1-best",
        verdict=True,
        best_score=88.9,
        init_score=84.3,
        metrics=[],
    )
    run = _run(
        "run-final",
        "completed",
        progress_unit=7,
        stats={
            "sessions": 4,
            "probes": 3,
            "usedProbes": 0,
            "clusters": 99,
            "byAttributeType": {"model": 1, "prompt": 1, "error": 0, "nonIssue": 1},
            "unknown": "ignored",
        },
    )
    service = EvolutionRunService(
        FakeRunStore((_summary(run, clusters=2, accepted=1, final=final),)),
    )

    card = (await service.list()).history[0]

    assert card.created_by == "Ada"
    assert card.stats.sessions == 4
    assert card.stats.probes == 3
    assert card.stats.used_probes == 2
    assert card.stats.clusters == 2
    assert card.stats.by_attribute_type.model == 1
    assert card.final is not None
    assert card.final.best_version == "v2.0.1-best"
    assert card.final.branch_name == "evo/run-final"
    assert card.final.push_status == "succeeded"
    assert card.final.verdict is True


async def test_failed_run_error_keeps_only_the_sanitized_summary() -> None:
    """Failed history exposes stage, message, and timestamp for a tooltip."""
    run = _run("run-failed", "failed", error=("eval", "sandbox timeout"))

    card = (
        await EvolutionRunService(
            FakeRunStore((_summary(run),)),
        ).list()
    ).history[0]

    assert card.error is not None
    assert card.error.stage == "eval"
    assert card.error.message == "sandbox timeout"
    assert card.error.at == NOW
