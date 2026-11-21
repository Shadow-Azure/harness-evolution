"""Read-only evolution run list projection owned by the backend."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Literal, Protocol, cast

from pydantic import Field

from app.db.models.evolution import EvolutionRunSummaryRecord
from app.service.evolution.state import (
    PREPARE_COMPLETE_UNIT,
    effective_unit,
    is_legacy_run,
    progress_total,
    step_states,
    total_units,
    validate_cursor,
)
from app.service.identity.schemas import IdentityModel

EvolutionRunStatus = Literal[
    "preparing",
    "running",
    "blocked",
    "completed",
    "failed",
    "interrupted",
]
EvolutionRunPushStatus = Literal[
    "pending",
    "pushing",
    "succeeded",
    "failed",
    "skipped",
]
EvolutionRunEvalStatus = Literal[
    "pending",
    "evaluating",
    "completed",
    "failed",
    "timeout",
]
EvolutionRunBlockedStage = Literal[
    "patch",
    "push",
    "eval",
    "attribution",
]
_RUNNING_STATUSES = frozenset({"preparing", "running", "blocked"})
_RUN_STAGE_LABELS = (
    "第 1/7 步 · 选择范围中…",
    "第 2/7 步 · Session 关联中…",
    "第 3/7 步 · 筛选潜在 bad case 中…",
    "第 4/7 步 · 对象归因中…",
    "第 5/7 步 · 聚类与严重度排序中…",
)
_CLUSTER_ONLY_STAGE_LABELS = (
    "第 1/5 步 · 选择范围中…",
    "第 2/5 步 · Session 关联中…",
    "第 3/5 步 · 筛选潜在 bad case 中…",
    "第 4/5 步 · 对象归因中…",
    "第 5/5 步 · 聚类与严重度排序中…",
)
_CLUSTER_ONLY_DONE_LABEL = "第 5/5 步 · 聚类完成"


class EvolutionRunTarget(IdentityModel):
    """Immutable evolution target snapshot shown on one run card."""

    type: Literal["skill", "agent", "knowledge"]
    name: str
    version: str
    target_revision: str | None = Field(
        default=None,
        description=(
            "Resolved file-matching revision (digest:<sha256(body)> for "
            "skill/agent/knowledge file targets); null on historical runs."
        ),
    )


class EvolutionRunWindow(IdentityModel):
    """Session-time window selected when the run was created."""

    start: date | None = Field(default=None, alias="from")
    to: date | None = None


class EvolutionRunPolicy(IdentityModel):
    """Display-only potential policy preset for one run card."""

    preset: Literal["default", "custom"] = "default"


class EvolutionRunError(IdentityModel):
    """Sanitized terminal or blocked error summary."""

    stage: str
    message: str
    at: datetime


class EvolutionRunAttributeStats(IdentityModel):
    """Case counts by the closed attribution category."""

    model: int = 0
    prompt: int = 0
    error: int = 0


class EvolutionRunStats(IdentityModel):
    """Backend-normalized V2 run statistics."""

    sessions: int = 0
    version_unresolved_sessions: int = 0
    bad_cases: int = 0
    potential: int = 0
    attributed: int = 0
    reused: int = 0
    clusters: int = 0
    by_category: EvolutionRunAttributeStats


class EvolutionRunProgress(IdentityModel):
    """Backend-owned cursor, percentages, rounds, and stage copy."""

    unit: int
    total: int
    percent: int
    stage_label: str
    done_rounds: int
    accepted: int


class EvolutionRunFinal(IdentityModel):
    """Terminal evaluation summary shown in the history list."""

    best_version: str
    branch_name: str | None
    push_status: EvolutionRunPushStatus
    verdict: bool
    best_score: float
    init_score: float


class EvolutionRunCard(IdentityModel):
    """One complete run-list card contract."""

    run_id: str
    title: str
    mode: Literal["full", "cluster_only"]
    target: EvolutionRunTarget
    window: EvolutionRunWindow
    models: list[str]
    policy: EvolutionRunPolicy
    cache_enabled: bool
    created_by: str | None
    created_at: datetime
    status: EvolutionRunStatus
    error: EvolutionRunError | None
    stats: EvolutionRunStats
    progress: EvolutionRunProgress
    final: EvolutionRunFinal | None


class EvolutionRunWorkspace(IdentityModel):
    """Repository and worktree state shown by the run detail."""

    repo_url: str
    push_repo_url: str
    sub_dir: str
    repo_path: str | None
    base_ref: str | None
    base_commit: str | None
    branch_name: str | None
    workspace_path: str | None
    remote: str
    push_status: EvolutionRunPushStatus
    pushed_at: datetime | None
    push_error: str | None


class EvolutionRunStep(IdentityModel):
    """One backend-owned stepper node with lazy-load eligibility."""

    index: int
    key: Literal[
        "range",
        "sessions",
        "potential",
        "attribution",
        "clusters",
        "iteration",
        "final",
    ]
    title: str
    status: Literal["done", "active", "pending"]
    clickable: bool
    detail: str | None = None


class EvolutionRunDetail(EvolutionRunCard):
    """Complete shell consumed by the seven-step run-detail page."""

    blocked_stage: EvolutionRunBlockedStage | None
    retry_attempts: int
    next_retry_at: datetime | None
    eval_status: EvolutionRunEvalStatus
    workspace: EvolutionRunWorkspace
    last_event_seq: int
    steps: list[EvolutionRunStep]


class EvolutionRunList(IdentityModel):
    """Running and history groups already ordered by the backend."""

    running: list[EvolutionRunCard]
    history: list[EvolutionRunCard]


class EvolutionRunStore(Protocol):
    """Persistence contract consumed by the run-list service."""

    async def list_summaries(
        self,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> tuple[EvolutionRunSummaryRecord, ...]:
        """Return all in-scope runs with batched list facts."""

    async def get_summary(
        self,
        run_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionRunSummaryRecord | None:
        """Return one in-scope run with its batched list facts."""


class EvolutionRunEventSeqReader(Protocol):
    """Read the persisted event high-water mark for one run shell."""

    async def max_seq(self, run_id: str) -> int:
        """Return the latest durable event sequence."""


def _non_negative_int(value: object) -> int:
    """Return one optional non-negative integer without coercing booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _stats(summary: EvolutionRunSummaryRecord) -> EvolutionRunStats:
    """Normalize V2 stats and synthesize them from legacy probe counts."""
    raw = summary.run.stats
    by_category_raw = raw.get("byCategory", raw.get("byAttributeType"))
    by_category = by_category_raw if isinstance(by_category_raw, Mapping) else {}
    category = EvolutionRunAttributeStats(
        model=_non_negative_int(by_category.get("model")),
        prompt=_non_negative_int(by_category.get("prompt")),
        error=_non_negative_int(by_category.get("error")),
    )
    legacy_prepared = is_legacy_run(summary.run.attribution_engine)
    used_probes = category.model + category.prompt + category.error
    if legacy_prepared:
        sessions = _non_negative_int(raw.get("sessions"))
        bad_cases = _non_negative_int(raw.get("probes"))
        potential = _non_negative_int(raw.get("usedProbes"))
        return EvolutionRunStats(
            sessions=sessions,
            bad_cases=bad_cases,
            potential=potential,
            attributed=potential,
            clusters=summary.cluster_count,
            by_category=category,
        )
    return EvolutionRunStats(
        sessions=_non_negative_int(raw.get("sessions")),
        version_unresolved_sessions=_non_negative_int(raw.get("versionUnresolvedSessions")),
        bad_cases=_non_negative_int(raw.get("badCases")),
        potential=_non_negative_int(raw.get("potential")),
        attributed=_non_negative_int(raw.get("attributed")) or used_probes,
        reused=_non_negative_int(raw.get("reused")),
        clusters=summary.cluster_count,
        by_category=category,
    )


def _progress(summary: EvolutionRunSummaryRecord) -> EvolutionRunProgress:
    """Derive every user-visible progress value from the persisted cursor."""
    run = summary.run
    cluster_count = summary.cluster_count
    validate_cursor(run.progress_unit, cluster_count)
    unit = effective_unit(
        run.progress_unit,
        cluster_count,
        attribution_engine=run.attribution_engine,
    )
    if run.mode == "cluster_only":
        total = progress_total(run.mode, cluster_count)
        unit = min(unit, total)
        stage_label = (
            _CLUSTER_ONLY_DONE_LABEL if unit >= total else _CLUSTER_ONLY_STAGE_LABELS[unit]
        )
        return EvolutionRunProgress(
            unit=unit,
            total=total,
            percent=math.floor(unit * 100 / total + 0.5),
            stage_label=stage_label,
            done_rounds=0,
            accepted=0,
        )
    total = total_units(cluster_count)
    if unit < PREPARE_COMPLETE_UNIT:
        stage_label = _RUN_STAGE_LABELS[unit]
    elif unit < PREPARE_COMPLETE_UNIT + cluster_count:
        stage_label = f"第 6/7 步 · 迭代优化 · 第 {unit - 4}/{cluster_count} 轮"
    else:
        stage_label = "第 7/7 步 · 测试集终评中…"
    return EvolutionRunProgress(
        unit=unit,
        total=total,
        percent=math.floor(unit * 100 / total + 0.5),
        stage_label=stage_label,
        done_rounds=min(max(unit - PREPARE_COMPLETE_UNIT, 0), cluster_count),
        accepted=summary.accepted_count,
    )


def _error(summary: EvolutionRunSummaryRecord) -> EvolutionRunError | None:
    """Return a complete error summary only when all persisted fields exist."""
    run = summary.run
    if run.error_stage is None or run.error_message is None or run.error_at is None:
        return None
    return EvolutionRunError(
        stage=run.error_stage,
        message=run.error_message,
        at=run.error_at,
    )


def _final(summary: EvolutionRunSummaryRecord) -> EvolutionRunFinal | None:
    """Map an optional terminal evaluation row with the run's publish state."""
    final = summary.final
    if final is None:
        return None
    return EvolutionRunFinal(
        best_version=final.best_version,
        branch_name=summary.run.branch_name,
        push_status=cast(EvolutionRunPushStatus, summary.run.push_status),
        verdict=final.verdict,
        best_score=final.best_score,
        init_score=final.init_score,
    )


def _policy(summary: EvolutionRunSummaryRecord) -> EvolutionRunPolicy:
    """Project the display preset from the persisted policy snapshot."""
    raw = summary.run.potential_policy
    preset = raw.get("preset") if isinstance(raw, Mapping) else None
    return EvolutionRunPolicy(preset="custom" if preset == "custom" else "default")


def _card(summary: EvolutionRunSummaryRecord) -> EvolutionRunCard:
    """Map one repository summary to the public list card."""
    run = summary.run
    return EvolutionRunCard(
        run_id=run.id,
        title=run.title,
        mode=cast(Literal["full", "cluster_only"], run.mode),
        target=EvolutionRunTarget(
            type=cast(Literal["skill", "agent", "knowledge"], run.target_type),
            name=run.target_name,
            version=run.target_version,
            target_revision=run.target_revision,
        ),
        window=EvolutionRunWindow.model_validate(
            {"from": run.window_from, "to": run.window_to},
        ),
        models=run.models,
        policy=_policy(summary),
        cache_enabled=run.cache_enabled,
        created_by=summary.created_by_name,
        created_at=run.created_at,
        status=cast(
            Literal[
                "preparing",
                "running",
                "blocked",
                "completed",
                "failed",
                "interrupted",
            ],
            run.status,
        ),
        error=_error(summary),
        stats=_stats(summary),
        progress=_progress(summary),
        final=_final(summary),
    )


def _detail_steps(
    summary: EvolutionRunSummaryRecord,
) -> list[EvolutionRunStep]:
    """Project the shared cursor state machine into stepper nodes."""
    run = summary.run
    states = step_states(
        run.progress_unit,
        summary.cluster_count,
        run.status,
        attribution_engine=run.attribution_engine,
    )
    unit = effective_unit(
        run.progress_unit,
        summary.cluster_count,
        attribution_engine=run.attribution_engine,
    )
    steps: list[EvolutionRunStep] = []
    for state in states:
        detail = None
        if state.key == "iteration" and state.status == "active" and summary.cluster_count > 0:
            round_number = min(
                max(unit - PREPARE_COMPLETE_UNIT + 1, 1),
                summary.cluster_count,
            )
            detail = f"第 {round_number}/{summary.cluster_count} 轮"
        steps.append(
            EvolutionRunStep(
                index=state.index,
                key=cast(
                    Literal[
                        "range",
                        "sessions",
                        "potential",
                        "attribution",
                        "clusters",
                        "iteration",
                        "final",
                    ],
                    state.key,
                ),
                title=state.title,
                status=state.status,
                clickable=state.clickable,
                detail=detail,
            ),
        )
    return steps


class EvolutionRunService:
    """Project repository summaries into backend-grouped run cards."""

    def __init__(
        self,
        store: EvolutionRunStore,
        events: EvolutionRunEventSeqReader | None = None,
    ) -> None:
        """Bind the service to its run summary store."""
        self._store = store
        self._events = events

    async def list(
        self,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionRunList:
        """Return repository-ordered running and history groups in scope."""
        if workspace_ids is None:
            summaries = await self._store.list_summaries()
        else:
            summaries = await self._store.list_summaries(workspace_ids=workspace_ids)
        cards = [_card(summary) for summary in summaries]
        return EvolutionRunList(
            running=[card for card in cards if card.status in _RUNNING_STATUSES],
            history=[card for card in cards if card.status not in _RUNNING_STATUSES],
        )

    async def detail(
        self,
        run_id: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionRunDetail | None:
        """Return one in-scope run shell with workspace and backend-owned steps."""
        if workspace_ids is None:
            summary = await self._store.get_summary(run_id)
        else:
            summary = await self._store.get_summary(
                run_id,
                workspace_ids=workspace_ids,
            )
        if summary is None:
            return None
        card = _card(summary)
        run = summary.run
        last_event_seq = await self._events.max_seq(run_id) if self._events is not None else 0
        return EvolutionRunDetail(
            **card.model_dump(),
            blocked_stage=cast(
                EvolutionRunBlockedStage | None,
                run.blocked_stage,
            ),
            retry_attempts=run.retry_attempts,
            next_retry_at=run.next_retry_at,
            eval_status=cast(EvolutionRunEvalStatus, run.eval_status),
            workspace=EvolutionRunWorkspace(
                repo_url=run.repo_url,
                push_repo_url=run.push_repo_url or run.repo_url,
                sub_dir=run.sub_dir,
                repo_path=run.repo_path,
                base_ref=run.base_ref,
                base_commit=run.base_commit,
                branch_name=run.branch_name,
                workspace_path=run.workspace_path,
                remote=run.remote_name,
                push_status=cast(EvolutionRunPushStatus, run.push_status),
                pushed_at=run.pushed_at,
                push_error=run.push_error,
            ),
            last_event_seq=last_event_seq,
            steps=_detail_steps(summary),
        )
