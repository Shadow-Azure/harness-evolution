"""V2 evolution preparation: sessions, potential, attribution, and clustering."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from app.db.crud.attributions import (
    AttributionRepository,
    CandidateWrite,
    EvolutionRunCandidateRepository,
)
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.potential import ObjectType, window_day_boundaries
from app.db.models.evolution import (
    ClusterWrite,
    EvolutionRunRecord,
    ProbeClusterRecord,
)
from app.db.models.jobs import JobRunRecord
from app.errors import AppError, ErrorCode
from app.service.evolution.attribution import AttributionRunner, AttributionRunSummary
from app.service.evolution.cluster import (
    CLUSTER_ALGORITHM,
    SIMILARITY_THRESHOLD,
    TYPE_CONFIDENCE,
    TYPE_IMPACT,
    ProbeForCluster,
    cluster_hash,
    cluster_probes,
    cluster_severity,
)
from app.service.evolution.engine.contracts import ConfigError, RunBlocked
from app.service.evolution.events import (
    EvolutionRunEventService,
    EvolutionRunEventStage,
    EvolutionRunEventType,
)
from app.service.evolution.git_failures import classify_git_failure
from app.service.evolution.potential import (
    AnchorSource,
    HitReason,
    MatchCondition,
    OrderState,
    PotentialCase,
    PotentialMatcher,
    ResolvedPolicy,
    SessionAssociation,
    TriggerPoint,
    resolve_policy,
    resolve_window,
)
from app.service.evolution.target_content import (
    ResolvedTargetVersion,
    TargetVersionResolver,
    resolve_legacy_target_version,
)
from app.third_party_api.git.workspace import GitOperationError, PreparedWorkspace
from app.utils.ids import new_id
from app.utils.redaction import sanitize_message
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

ATTRIBUTION_EVENT_BATCH = 20
"""Batched attribution event size from 07 §5.11."""


class PrepareEventRecorder(Protocol):
    """Durable event operations consumed by prepare orchestration."""

    async def record(
        self,
        run_id: str,
        event_type: EvolutionRunEventType,
        *,
        level: str,
        stage: EvolutionRunEventStage,
        message: str,
        step_index: int | None = None,
        cluster_id: str | None = None,
        round_id: str | None = None,
        job_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> object:
        """Append one sanitized phase event."""


class WorkspacePreparer(Protocol):
    """Git workspace operations consumed by prepare orchestration."""

    async def prepare(self, run: EvolutionRunRecord) -> PreparedWorkspace:
        """Prepare one isolated repository workspace."""


class AttributionBatchDispatcher(Protocol):
    """Durable attribution lane shared with manual and scheduled entrypoints."""

    async def run_for_prepare(self, run: EvolutionRunRecord) -> AttributionRunSummary:
        """Submit or join the run's idempotent attribution batch."""


@dataclass(slots=True)
class _PrepareContext:
    """Mutable facts shared across the seven prepare stages."""

    association: SessionAssociation | None = None
    summary: AttributionRunSummary | None = None


class EvolutionPrepareService:
    """Run the V2 seven-stage prepare workflow through durable repositories."""

    def __init__(
        self,
        runs: EvolutionRepository,
        candidates: EvolutionRunCandidateRepository,
        attributions: AttributionRepository,
        matcher: PotentialMatcher,
        attribution: AttributionRunner,
        workspaces: WorkspacePreparer,
        events: PrepareEventRecorder | EvolutionRunEventService | None = None,
        resolver: TargetVersionResolver | None = None,
        *,
        attribution_jobs: AttributionBatchDispatcher | None = None,
    ) -> None:
        """Bind persistence, the shared matcher, the runner, and git workspaces."""
        self._runs = runs
        self._candidates = candidates
        self._attributions = attributions
        self._matcher = matcher
        self._attribution = attribution
        self._workspaces = workspaces
        self._events = events
        self._attribution_jobs = attribution_jobs
        self._resolver = resolver

    async def handle(self, job: JobRunRecord) -> Mapping[str, Any]:
        """Prepare one run idempotently and return its durable summary."""
        run_id = job.ref_id or _payload_run_id(job.payload)
        run = await self._runs.get_run(run_id)
        if run is None:
            raise LookupError("evolution run not found")
        if await self._already_prepared(run):
            return {
                "runId": run.id,
                "status": run.status,
                "progressUnit": run.progress_unit,
                "reused": True,
            }
        resolved = await self._resolve_target(run)
        persist_revision = run.target_revision is None and self._resolver is not None

        context = _PrepareContext()
        if run.progress_unit == 0:
            await self._record(
                run.id,
                "prepare_started",
                stage="prepare",
                message="准备阶段已启动",
                job_id=job.id,
            )
            run = await self._runs.advance_unit(
                run.id,
                expected=0,
                target=1,
                cluster_count=0,
            )

        if run.progress_unit < 2:
            condition = self._condition(run, resolved)
            association = await self._matcher.associated_sessions(condition)
            context.association = association
            if not association.sessions:
                raise AppError(
                    status_code=409,
                    code=ErrorCode.NO_ASSOCIATED_SESSIONS,
                    message="no Session contains the requested object version",
                    details={"summary": _association_summary(association)},
                )
            await self._runs.write_stats(
                run.id,
                {
                    **dict(run.stats),
                    "reportedSessions": association.reported,
                    "sessions": association.associated,
                    "skippedSessions": association.skipped,
                    "versionUnresolvedSessions": association.version_unresolved,
                    "pendingSessions": association.pending,
                    "sessionRows": [
                        {
                            "sessionId": session.session_id,
                            "title": session.title,
                            "objectTriggerAt": session.object_trigger_at.isoformat(),
                            "badCaseCount": session.bad_case_count,
                        }
                        for session in association.sessions
                    ],
                },
            )
            await self._record(
                run.id,
                "sessions_linked",
                stage="prepare",
                step_index=1,
                message=(
                    "Session 关联完成："  # noqa: RUF001
                    f"关联 {association.associated} / 上报 {association.reported}"
                ),
                job_id=job.id,
                payload=_association_summary(association),
            )
            run = await self._runs.advance_unit(
                run.id,
                expected=1,
                target=2,
                cluster_count=0,
            )

        if run.progress_unit < 3:
            condition = self._condition(run, resolved)
            association = context.association or await self._matcher.associated_sessions(condition)
            context.association = association
            policy = _run_policy(run)
            match = await self._matcher.potential_cases(condition, association, policy)
            await self._candidates.upsert_many(_candidate_writes(run, match.cases))
            stats = _potential_stats(run, association, match.cases, match.potential)
            await self._runs.write_stats(run.id, stats)
            if not match.included:
                raise AppError(
                    status_code=409,
                    code=ErrorCode.NO_POTENTIAL_MATCHED,
                    message="no potential bad case matches the run policy",
                    details={"summary": _potential_summary(stats)},
                )
            await self._record(
                run.id,
                "potential_computed",
                stage="prepare",
                step_index=2,
                message=f"潜在 bad case 筛选完成：{match.potential} 个",  # noqa: RUF001,
                job_id=job.id,
                payload=_potential_summary(stats),
            )
            run = await self._runs.advance_unit(
                run.id,
                expected=2,
                target=3,
                cluster_count=0,
            )

        if run.progress_unit < 4:
            candidates = await self._candidates_from_rows(run)
            try:
                summary = (
                    await self._attribution_jobs.run_for_prepare(run)
                    if self._attribution_jobs is not None
                    else await self._attribution.run(
                        run,
                        candidates,
                        run.cache_enabled,
                        target_revision=resolved.target_revision,
                    )
                )
            except RunBlocked:
                raise
            except (ConfigError, ValueError):
                raise
            except Exception as exc:
                raise RunBlocked(
                    "attribution failed",
                    stage="attribution",
                    error_stage="prepare",
                    retryable=True,
                ) from exc
            context.summary = summary
            stats = dict(run.stats)
            stats.update(
                {
                    "attributed": await self._attributed_count(run),
                    "reused": summary.reused,
                    "byCategory": await self._category_counts(run),
                },
            )
            await self._runs.write_stats(run.id, stats)
            await self._record_attribution_batches(run, summary, job.id)
            run = await self._runs.advance_unit(
                run.id,
                expected=3,
                target=4,
                cluster_count=0,
            )

        if run.progress_unit < 5:
            clusters, fingerprint = await self._build_clusters(run)
            stats = dict(run.stats)
            stats.update(
                {
                    "clusters": len(clusters),
                    "byCategory": await self._category_counts(run),
                },
            )
            await self._runs.write_stats(run.id, stats)
            await self._record(
                run.id,
                "clusters_created",
                stage="cluster",
                step_index=4,
                message=f"聚类完成：{len(clusters)} 个簇",  # noqa: RUF001
                job_id=job.id,
                payload={
                    "clusters": len(clusters),
                    "algorithm": CLUSTER_ALGORITHM,
                    "similarityThreshold": SIMILARITY_THRESHOLD,
                    "clusterHash": fingerprint,
                },
            )

        workspace = None
        if run.mode == "full":
            workspace = await self._prepare_workspace(run, job)
            await self._build_rounds(run)
        refreshed = await self._runs.get_run(run.id)
        prepared = await self._runs.mark_prepared(
            run.id,
            status="running" if run.mode == "full" else "completed",
            progress_unit=5,
            repo_path=str(workspace.repo_path) if workspace else run.repo_path,
            base_ref=workspace.ref if workspace else run.base_ref,
            base_commit=workspace.base_commit if workspace else run.base_commit,
            branch_name=workspace.branch if workspace else run.branch_name,
            workspace_path=str(workspace.path) if workspace else run.workspace_path,
            target_revision=(resolved.target_revision if persist_revision else None),
            stats=await self._final_stats(refreshed or run),
        )
        return {
            "runId": prepared.id,
            "status": prepared.status,
            "progressUnit": prepared.progress_unit,
            "clusters": len(await self._runs.list_clusters(prepared.id)),
            "rounds": (len(await self._runs.list_rounds(prepared.id)) if run.mode == "full" else 0),
        }

    async def _resolve_target(self, run: EvolutionRunRecord) -> ResolvedTargetVersion:
        """Resolve the run target once so matching and attribution share one identity."""
        if run.target_revision:
            return ResolvedTargetVersion(run.target_version, run.target_revision)
        if self._resolver is None:
            return resolve_legacy_target_version(run.target_version)
        return await self._resolver.resolve(
            object_type=run.target_type,
            repo_url=run.repo_url,
            sub_dir=run.sub_dir,
            version=run.target_version,
        )

    def _condition(
        self,
        run: EvolutionRunRecord,
        resolved: ResolvedTargetVersion,
    ) -> MatchCondition:
        """Build the matcher condition from the run snapshot and resolved revision."""
        start, end = resolve_window(run.window_from, run.window_to)
        window_start, window_end = window_day_boundaries(start, end)
        return MatchCondition(
            workspace_id=run.workspace_id,
            target_type=cast(ObjectType, run.target_type),
            target_name=run.target_name,
            target_version=resolved.target_version,
            target_revision=resolved.target_revision,
            window_start=window_start,
            window_end=window_end,
        )

    async def _already_prepared(self, run: EvolutionRunRecord) -> bool:
        """Detect a retried prepare that already committed this exact workflow."""
        if run.progress_unit < 5:
            return False
        if run.mode == "cluster_only":
            return run.status == "completed"
        if run.status == "preparing":
            return False
        return bool(await self._runs.list_rounds(run.id))

    async def _build_clusters(
        self,
        run: EvolutionRunRecord,
    ) -> tuple[tuple[ProbeClusterRecord, ...], str]:
        """Cluster attributed candidates, persist scores, and return the audit hash."""
        rows = await self._attributions.list_clusterable_probes(run.id)
        cases_by_probe: dict[str, set[str]] = {}
        type_by_probe: dict[str, str] = {}
        for probe_id, attribute_type, bad_case_id in rows:
            type_by_probe[probe_id] = attribute_type
            cases_by_probe.setdefault(probe_id, set()).add(bad_case_id)
        evidence_case_ids = tuple(dict.fromkeys(bad_case_id for _, _, bad_case_id in rows))
        evidence = await self._attributions.load_bad_case_evidence(evidence_case_ids)
        title_by_probe = {
            probe_id: (
                evidence[case_id].title if (case_id := min(probe_case_ids)) in evidence else ""
            )
            for probe_id, probe_case_ids in cases_by_probe.items()
        }
        drafts = cluster_probes(
            tuple(
                ProbeForCluster(
                    probe_id=probe_id,
                    attribute_type=cast(Any, type_by_probe[probe_id]),
                    text=title_by_probe.get(probe_id, ""),
                )
                for probe_id in dict.fromkeys(probe_id for probe_id, _, _ in rows)
                if type_by_probe.get(probe_id) in TYPE_CONFIDENCE
            ),
        )
        scored: list[tuple[float, int, ClusterWrite]] = []
        for draft in drafts:
            case_ids = {
                bad_case_id
                for probe_id in draft.probes
                for bad_case_id in cases_by_probe.get(probe_id, set())
            }
            scored.append(
                (
                    cluster_severity(draft.type, len(case_ids)),
                    len(case_ids),
                    ClusterWrite(
                        type=draft.type,
                        description=draft.description,
                        probes=draft.probes,
                        impact=float(TYPE_IMPACT[draft.type]),
                        confidence=TYPE_CONFIDENCE[draft.type],
                    ),
                ),
            )
        ordered = sorted(
            scored,
            key=lambda item: (-item[0], -item[1], item[2].type),
        )
        writes = tuple(
            ClusterWrite(
                type=item[2].type,
                description=item[2].description,
                probes=item[2].probes,
                impact=item[2].impact,
                confidence=item[2].confidence,
                severity=item[0],
                rank=rank,
            )
            for rank, item in enumerate(ordered, start=1)
        )
        persisted = await self._runs.replace_prepared_clusters(run.id, writes)
        return persisted, cluster_hash(drafts)

    async def _prepare_workspace(
        self,
        run: EvolutionRunRecord,
        job: JobRunRecord,
    ) -> PreparedWorkspace:
        """Prepare the isolated git workspace, mapping failures to blocked/failed."""
        try:
            workspace = await self._workspaces.prepare(run)
        except GitOperationError as exc:
            disposition = classify_git_failure(exc)
            if disposition.action == "blocked" and disposition.blocked_stage is not None:
                await self._runs.mark_blocked(
                    run.id,
                    stage=disposition.blocked_stage,
                    message=sanitize_message(str(exc), limit=2_000),
                    error_stage=disposition.error_stage,
                )
                raise RunBlocked(
                    "run branch publication failed",
                    stage=disposition.blocked_stage,
                    error_stage=disposition.error_stage,
                ) from None
            raise
        await self._record(
            run.id,
            "workspace_prepared",
            stage="prepare",
            message="隔离 workspace 与 run 分支已准备",
            job_id=job.id,
            payload={
                "baseCommit": workspace.base_commit,
                "branch": workspace.branch,
            },
        )
        return workspace

    async def _build_rounds(self, run: EvolutionRunRecord) -> None:
        """Create one pending round per cluster for a full run exactly once."""
        clusters = await self._runs.list_clusters(run.id)
        ordered = sorted(
            clusters,
            key=lambda cluster: (cluster.rank or 0, cluster.seq),
        )
        existing_rounds = await self._runs.list_rounds(run.id)
        if not existing_rounds:
            await self._runs.insert_rounds(
                tuple(
                    {
                        "id": new_id(),
                        "run_id": run.id,
                        "probe_cluster_id": cluster.probe_cluster_id,
                        "seq": seq,
                        "status": "pending",
                    }
                    for seq, cluster in enumerate(ordered, start=1)
                ),
            )
        elif len(existing_rounds) != len(ordered):
            raise AppError(
                status_code=409,
                code=ErrorCode.VALIDATION_INVALID,
                message="prepared run has an incomplete round snapshot",
            )

    async def _candidates_from_rows(
        self,
        run: EvolutionRunRecord,
    ) -> tuple[PotentialCase, ...]:
        """Reconstruct included matcher rows from stored candidates on retry."""
        rows = await self._candidates.list(run.id)
        included = [row for row in rows if row.included]
        evidence = await self._attributions.load_bad_case_evidence(
            tuple(row.bad_case_id for row in included),
        )
        candidates: list[PotentialCase] = []
        for row in included:
            case = evidence.get(row.bad_case_id)
            candidates.append(
                PotentialCase(
                    bad_case_id=row.bad_case_id,
                    session_id=row.session_id,
                    object_name=run.target_name,
                    bad_case_type=case.bad_case_type if case is not None else "self",
                    trigger_at=row.case_trigger_at or row.created_at,
                    hit_reason=cast(HitReason, row.included_reason),
                    order_state=cast(OrderState, row.order_state),
                    included=True,
                    object_trigger=_trigger_point(
                        row.object_trigger_agent_id,
                        row.object_trigger_event_index,
                        row.object_trigger_at,
                    ),
                    case_trigger=(
                        _trigger_point(
                            row.case_trigger_agent_id,
                            row.case_trigger_event_index,
                            row.case_trigger_at,
                        )
                        if row.case_trigger_agent_id is not None
                        or row.case_trigger_event_index is not None
                        or row.case_trigger_at is not None
                        else None
                    ),
                    anchor_source=cast(AnchorSource, row.case_anchor_kind or "unknown"),
                ),
            )
        return tuple(candidates)

    async def _attributed_count(self, run: EvolutionRunRecord) -> int:
        """Count distinct included bad cases with an attributed conclusion."""
        rows = await self._attributions.list_clusterable_probes(run.id)
        return len({bad_case_id for _, _, bad_case_id in rows})

    async def _category_counts(self, run: EvolutionRunRecord) -> dict[str, int]:
        """Count attributed probes by their closed category."""
        rows = await self._attributions.list_clusterable_probes(run.id)
        counts = dict.fromkeys(TYPE_CONFIDENCE, 0)
        for _, attribute_type, _ in rows:
            if attribute_type in counts:
                counts[attribute_type] += 1
        return counts

    async def _record_attribution_batches(
        self,
        run: EvolutionRunRecord,
        summary: AttributionRunSummary,
        job_id: str | None,
    ) -> None:
        """Record attribution outcomes in bounded batches from 07 §5.11."""
        for created, offset in _batches(summary.created):
            await self._record(
                run.id,
                "attribution_created",
                stage="prepare",
                step_index=3,
                message=f"归因生成：{created} 条",  # noqa: RUF001,
                job_id=job_id,
                payload={"count": created, "offset": offset},
            )
        for reused, offset in _batches(summary.reused):
            await self._record(
                run.id,
                "attribution_reused",
                stage="prepare",
                step_index=3,
                message=f"缓存复用：{reused} 条",  # noqa: RUF001,
                job_id=job_id,
                payload={"count": reused, "offset": offset},
            )

    async def _final_stats(self, run: EvolutionRunRecord) -> dict[str, Any]:
        """Return the complete persisted V2 stats after a successful prepare."""
        stats = dict(run.stats)
        stats["attributed"] = await self._attributed_count(run)
        stats["byCategory"] = await self._category_counts(run)
        return stats

    async def _record(
        self,
        run_id: str,
        event_type: EvolutionRunEventType,
        *,
        stage: EvolutionRunEventStage,
        message: str,
        job_id: str | None = None,
        step_index: int | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        """Record one best-effort phase event without masking domain work."""
        if self._events is None:
            return
        try:
            await self._events.record(
                run_id,
                event_type,
                level="info",
                stage=stage,
                message=message,
                step_index=step_index,
                job_id=job_id,
                payload=payload,
            )
        except Exception:
            logger.exception(
                "failed to record prepare event",
                extra={"run_id": run_id, "event_type": event_type},
            )


def _run_policy(run: EvolutionRunRecord) -> ResolvedPolicy:
    """Read the resolved policy snapshot without re-validating a default preset."""
    raw = run.potential_policy
    if raw is None:
        return resolve_policy(None)
    if not isinstance(raw, Mapping):
        raise ConfigError("run potential policy snapshot must be an object")
    preset = raw.get("preset")
    if preset not in {"default", "custom"}:
        raise ConfigError("run potential policy snapshot has an unknown preset")
    return ResolvedPolicy(
        preset=preset,
        include_self_report=bool(raw.get("includeSelfReport", True)),
        include_after_object=bool(raw.get("includeAfterObject", True)),
        same_object_only=bool(raw.get("sameObjectOnly", False)),
    )


def _candidate_writes(
    run: EvolutionRunRecord,
    cases: Sequence[PotentialCase],
) -> tuple[CandidateWrite, ...]:
    """Map every evaluated matcher case to one idempotent candidate row."""
    now = now_shanghai()
    return tuple(
        CandidateWrite(
            id=new_id(),
            run_id=run.id,
            workspace_id=run.workspace_id,
            session_id=case.session_id,
            bad_case_id=case.bad_case_id,
            order_state=case.order_state,
            included=case.included,
            included_reason=case.hit_reason,
            created_at=now,
            object_trigger_agent_id=case.object_trigger.agent_id,
            object_trigger_event_index=case.object_trigger.event_index,
            object_trigger_at=case.object_trigger.triggered_at,
            case_trigger_agent_id=(
                case.case_trigger.agent_id if case.case_trigger is not None else None
            ),
            case_trigger_event_index=(
                case.case_trigger.event_index if case.case_trigger is not None else None
            ),
            case_anchor_kind=case.anchor_source,
            case_trigger_at=(
                case.case_trigger.triggered_at if case.case_trigger is not None else None
            ),
        )
        for case in cases
    )


def _trigger_point(
    agent_id: str | None,
    event_index: int | None,
    triggered_at: datetime | None,
) -> TriggerPoint:
    """Rebuild one stored trigger coordinate without inventing order."""
    return TriggerPoint(
        agent_id=agent_id,
        event_index=event_index,
        triggered_at=triggered_at,
        tree_index=None,
    )


def _association_summary(association: SessionAssociation) -> dict[str, int]:
    """Map the matcher partition to the persisted session summary."""
    return {
        "reported": association.reported,
        "associated": association.associated,
        "skipped": association.skipped,
        "versionUnresolved": association.version_unresolved,
        "pending": association.pending,
    }


def _potential_stats(
    run: EvolutionRunRecord,
    association: SessionAssociation,
    cases: Sequence[PotentialCase],
    potential: int,
) -> dict[str, Any]:
    """Build the incremental stats snapshot after the potential stage."""
    by_reason = {
        "self_report": 0,
        "after_object": 0,
        "both": 0,
        "policy_excluded": 0,
        "order_unknown": 0,
    }
    for case in cases:
        by_reason[case.hit_reason] += 1
    return {
        **dict(run.stats),
        "sessions": association.associated,
        "versionUnresolvedSessions": association.version_unresolved,
        "badCases": len(cases),
        "potential": potential,
        "byReason": by_reason,
    }


def _potential_summary(stats: Mapping[str, Any]) -> dict[str, Any]:
    """Return the public potential summary persisted in stats."""
    raw_reasons = stats.get("byReason")
    by_reason = raw_reasons if isinstance(raw_reasons, Mapping) else {}
    return {
        "badCases": stats.get("badCases", 0),
        "potential": stats.get("potential", 0),
        "byReason": {
            key: int(by_reason.get(key, 0))
            for key in (
                "self_report",
                "after_object",
                "both",
                "policy_excluded",
                "order_unknown",
            )
        },
    }


def _batches(total: int) -> tuple[tuple[int, int], ...]:
    """Split one outcome count into bounded attribution event batches."""
    return tuple(
        (min(ATTRIBUTION_EVENT_BATCH, total - offset), offset)
        for offset in range(0, total, ATTRIBUTION_EVENT_BATCH)
    )


def _payload_run_id(payload: Mapping[str, Any]) -> str:
    """Read the camelCase run identifier used by queued launch jobs."""
    value = payload.get("runId", payload.get("run_id"))
    if isinstance(value, str) and value:
        return value
    raise ValueError("evolution prepare job has no run id")


__all__ = ["EvolutionPrepareService"]
