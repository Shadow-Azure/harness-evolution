"""V2 evolution preparation: sessions, potential, attribution, and clustering."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast
from urllib.parse import urlsplit

from pydantic import TypeAdapter

from app.db.crud.attributions import (
    AttributionRepository,
    BadCaseEvidenceRecord,
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
from app.service.evolution.ai_observability import AiAgentCall
from app.service.evolution.attribution import AttributionRunner, AttributionRunSummary
from app.service.evolution.attribution_jobs import candidate_snapshot
from app.service.evolution.candidate_policy import CandidatePolicy
from app.service.evolution.cluster import (
    ATTRIBUTION_DRAFT_MAX_CHARS,
    ATTRIBUTION_HYBRID_ALGORITHM,
    LEXICAL_ALGORITHM,
    SIMILARITY_THRESHOLD,
    TYPE_CONFIDENCE,
    TYPE_IMPACT,
    ClusterDraft,
    ProbeForCluster,
    build_attribution_drafts,
    cluster_hash,
    cluster_probes,
    cluster_severity,
)
from app.service.evolution.cluster_llm import (
    CallRecord,
    ClusterCaseEvidence,
    ClusterDraftStats,
    DegradedCall,
    EnhancedCluster,
    EnhancedClusters,
    enhance_clusters,
)
from app.service.evolution.control import checkpoint
from app.service.evolution.engine.contracts import ConfigError, RunBlocked
from app.service.evolution.events import (
    EvolutionRunEventLevel,
    EvolutionRunEventService,
    EvolutionRunEventStage,
    EvolutionRunEventType,
)
from app.service.evolution.git_failures import classify_git_failure
from app.service.evolution.potential import (
    MatchCondition,
    PotentialCase,
    PotentialMatcher,
    ResolvedPolicy,
    SessionAssociation,
    resolve_policy,
    resolve_window,
)
from app.service.evolution.target_content import (
    ResolvedTargetVersion,
    TargetVersionResolver,
    prefixed_revision,
    resolve_legacy_target_version,
)
from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.git.observability import (
    GitOperationCollector,
    git_operation_scope,
)
from app.third_party_api.git.workspace import GitOperationError, PreparedWorkspace
from app.utils.ids import new_id
from app.utils.redaction import sanitize_message
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

_ASSOCIATION = TypeAdapter(SessionAssociation)

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


@dataclass(frozen=True, slots=True)
class _ClusterBuild:
    """Durable result of one clustering step, including its audit identity."""

    clusters: tuple[ProbeClusterRecord, ...]
    fingerprint: str
    algorithm: str
    draft_count: int = 0
    severity_comparison: tuple[dict[str, Any], ...] = ()
    degraded: tuple[str, ...] = ()


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
        agent: AIAgentProvider | None = None,
        failure_policy: Literal["strict", "degrade"] = "degrade",
        *,
        attribution_jobs: AttributionBatchDispatcher | None = None,
    ) -> None:
        """Bind persistence, the shared matcher, the runner, git workspaces, and the agent.

        ``agent`` is optional: without a provider the prepare workflow keeps the
        legacy lexical clustering path byte for byte, which is what existing
        callers and tests rely on. ``failure_policy`` applies only to the bound
        agent path: ``strict`` fails the run on the first failed cluster task.
        """
        self._runs = runs
        self._candidates = candidates
        self._attributions = attributions
        self._matcher = matcher
        self._attribution = attribution
        self._workspaces = workspaces
        self._events = events
        self._attribution_jobs = attribution_jobs
        self._resolver = resolver
        self._agent = agent
        self._failure_policy = failure_policy

    async def handle(self, job: JobRunRecord) -> Mapping[str, Any]:
        """Prepare one run idempotently and return its durable summary."""
        run_id = job.ref_id or _payload_run_id(job.payload)
        run = await self._runs.get_run(run_id)
        if run is None:
            raise LookupError("evolution run not found")
        if run.status == "interrupted":
            await self._runs.mark_recovered(run.id)
            refreshed = await self._runs.get_run(run.id)
            if refreshed is not None:
                run = refreshed
        if await self._already_prepared(run):
            return {
                "runId": run.id,
                "status": run.status,
                "progressUnit": run.progress_unit,
                "reused": True,
            }
        await checkpoint(self._runs, run.id)
        resolved = await self._resolve_target(run) if run.progress_unit < 4 else None
        if resolved and run.target_revision is None and self._resolver is not None:
            await self._runs.freeze_revision(run.id, resolved.target_revision)

        context = _PrepareContext()
        await checkpoint(self._runs, run.id)
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

        await checkpoint(self._runs, run.id)
        if resolved is not None and run.progress_unit < 2:
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
            run = await self._runs.advance_unit(
                run.id,
                expected=1,
                target=2,
                cluster_count=0,
                stats={
                    **dict(run.stats),
                    "associationSnapshot": _ASSOCIATION.dump_python(association, mode="json"),
                    "reportedSessions": association.reported,
                    "sessions": association.associated,
                    "skippedSessions": association.skipped,
                    "versionUnresolvedSessions": association.version_unresolved,
                    "pendingSessions": association.pending,
                    "sessionRows": [
                        {
                            "sessionId": session.session_id,
                            "title": session.title,
                            "short": session.short,
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

        await checkpoint(self._runs, run.id)
        if resolved is not None and run.progress_unit < 3:
            condition = self._condition(run, resolved)
            if context.association is None:
                snapshot = run.stats.get("associationSnapshot")
                if snapshot is None and run.resumed_at:
                    raise ConfigError("Cannot resume without the frozen association snapshot")
                association = (
                    _ASSOCIATION.validate_python(snapshot)
                    if snapshot is not None
                    else await self._matcher.associated_sessions(condition)
                )
            else:
                association = context.association
            context.association = association
            policy = _run_policy(run)
            match = await self._matcher.potential_cases(condition, association, policy)
            await self._candidates.upsert_many(_candidate_writes(run, match.cases))
            stats = _potential_stats(run, association, match.cases, match.potential)
            if not match.included:
                await self._runs.write_stats(run.id, stats)
                raise AppError(
                    status_code=409,
                    code=ErrorCode.NO_POTENTIAL_MATCHED,
                    message="no potential bad case matches the run policy",
                    details={"summary": _potential_summary(stats)},
                )
            stats.pop("associationSnapshot", None)
            run = await self._runs.advance_unit(
                run.id, expected=2, target=3, cluster_count=0, stats=stats
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

        await checkpoint(self._runs, run.id)
        if resolved is not None and run.progress_unit < 4:
            if self._attribution_jobs is not None:
                summary = await self._attribution_jobs.run_for_prepare(run)
                await self._record_attribution_batches(run, summary, job.id)
                await checkpoint(self._runs, run.id)
            else:
                candidates = await candidate_snapshot(run, self._candidates, self._attributions)
                for offset in range(0, len(candidates), ATTRIBUTION_EVENT_BATCH):
                    batch = candidates[offset : offset + ATTRIBUTION_EVENT_BATCH]
                    try:
                        summary = await self._attribution.run(
                            run,
                            batch,
                            run.cache_enabled,
                            target_revision=resolved.target_revision,
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
                    await self._record_attribution_batches(run, summary, job.id)
                    await checkpoint(self._runs, run.id)
            rows = await self._candidates.list(run.id)
            stats = dict(run.stats)
            stats.update(
                {
                    "attributed": await self._attributed_count(run),
                    "reused": sum(row.is_cached for row in rows),
                    "byCategory": await self._category_counts(run),
                }
            )
            await self._runs.write_stats(run.id, stats)
            run = await self._runs.advance_unit(
                run.id,
                expected=3,
                target=4,
                cluster_count=0,
            )

        await checkpoint(self._runs, run.id)
        if run.progress_unit < 5:
            # Persist the policy before the first model call so a strict failure
            # is still explainable from the run snapshot and the step payload.
            if run.stats.get("clusterFailurePolicy") != self._failure_policy:
                await self._runs.write_stats(
                    run.id,
                    {**dict(run.stats), "clusterFailurePolicy": self._failure_policy},
                )
                run = await self._runs.get_run(run.id) or run
            built = await self._build_clusters(run)
            stats = dict(run.stats)
            stats.update(
                {
                    "clusters": len(built.clusters),
                    "byCategory": await self._category_counts(run),
                    "clusterAlgorithm": built.algorithm,
                    "clusterFailurePolicy": self._failure_policy,
                    "clusterDegraded": list(built.degraded),
                },
            )
            await self._runs.write_stats(run.id, stats)
            payload: dict[str, Any] = {
                "clusters": len(built.clusters),
                "algorithm": built.algorithm,
                "clusterHash": built.fingerprint,
            }
            if built.algorithm == LEXICAL_ALGORITHM:
                payload["similarityThreshold"] = SIMILARITY_THRESHOLD
            else:
                payload["draftCount"] = built.draft_count
                payload["draftSummaryMaxChars"] = ATTRIBUTION_DRAFT_MAX_CHARS
                payload["grouping"] = "one-draft-per-attribution"
            if built.severity_comparison:
                payload["severityFormula"] = [dict(item) for item in built.severity_comparison]
            if built.degraded:
                payload["degraded"] = list(built.degraded)
            await self._record(
                run.id,
                "clusters_created",
                stage="cluster",
                step_index=4,
                message=f"聚类完成：{len(built.clusters)} 个簇",  # noqa: RUF001
                job_id=job.id,
                payload=payload,
            )

        await checkpoint(self._runs, run.id)
        workspace = None
        if run.mode == "full":
            if not (run.stats.get("workspacePrepared") and run.workspace_path and run.base_commit):
                workspace = await self._prepare_workspace(run, job)
                await self._runs.write_workspace_checkpoint(
                    run.id,
                    repo_path=str(workspace.repo_path),
                    base_ref=workspace.ref,
                    base_commit=workspace.base_commit,
                    branch_name=workspace.branch,
                    workspace_path=str(workspace.path),
                    push_repo_url=workspace.push_url or "",
                    prepared=True,
                )
                await checkpoint(self._runs, run.id)
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
            push_repo_url=(workspace.push_url if workspace else None),
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
        if run.resumed_at:
            if prefixed_revision(run.target_version):
                return resolve_legacy_target_version(run.target_version)
            if not run.base_commit or self._resolver is None:
                raise ConfigError("Cannot resume without a frozen target revision or commit")
            pinned = await self._resolver.resolve(
                object_type=run.target_type,
                repo_url=run.repo_url,
                sub_dir=run.sub_dir,
                version=run.base_commit,
            )
            return ResolvedTargetVersion(
                run.target_version, pinned.target_revision, run.base_commit
            )
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
        start, end = resolve_window(run.window_from, run.window_to, today=run.created_at.date())
        window_start, window_end = window_day_boundaries(start, end)
        return MatchCondition(
            workspace_id=run.workspace_id,
            target_type=cast(ObjectType, run.target_type),
            target_name=run.target_name,
            target_version=resolved.target_version,
            target_revision=resolved.target_revision,
            window_start=window_start,
            candidate_policy=CandidatePolicy.model_validate(
                (run.potential_policy or {})["candidatePolicy"]
            )
            if (run.potential_policy or {}).get("candidatePolicy")
            else None,
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

    async def _build_clusters(self, run: EvolutionRunRecord) -> _ClusterBuild:
        """Cluster attributed candidates, persist scores, and return the audit facts.

        Without a bound agent this is the legacy lexical path: the same drafts,
        the same constants, the same rank order, and the same hash. With an
        agent every attributed probe becomes its own draft and the review layer
        merges drafts by shared root cause; the algorithm identity becomes
        ``hybrid-attribution-llm-v1``.
        """
        rows = await self._attributions.list_clusterable_probes(run.id)
        cases_by_probe: dict[str, set[str]] = {}
        for row in rows:
            cases_by_probe.setdefault(row.probe_id, set()).add(row.bad_case_id)
        evidence_case_ids = tuple(dict.fromkeys(row.bad_case_id for row in rows))
        evidence = await self._attributions.load_bad_case_evidence(evidence_case_ids)
        agent = self._agent
        if agent is None:
            title_by_probe = {
                probe_id: (
                    evidence[case_id].title if (case_id := min(case_ids)) in evidence else ""
                )
                for probe_id, case_ids in cases_by_probe.items()
            }
            drafts = cluster_probes(
                tuple(
                    ProbeForCluster(
                        probe_id=row.probe_id,
                        attribute_type=cast(Any, row.attribute_type),
                        text=title_by_probe.get(row.probe_id, ""),
                    )
                    for row in rows
                    if row.attribute_type in TYPE_CONFIDENCE
                ),
            )
            writes = _lexical_writes(drafts, cases_by_probe)
            persisted = await self._runs.replace_prepared_clusters(run.id, writes)
            return _ClusterBuild(
                clusters=persisted,
                fingerprint=cluster_hash(drafts),
                algorithm=LEXICAL_ALGORITHM,
                draft_count=len(drafts),
            )
        drafts = build_attribution_drafts(
            tuple(
                ProbeForCluster(
                    probe_id=row.probe_id,
                    attribute_type=cast(Any, row.attribute_type),
                    text=row.probe_description,
                )
                for row in rows
                if row.attribute_type in TYPE_CONFIDENCE
            ),
        )
        enhanced = await self._enhance_clusters(
            run,
            agent,
            drafts,
            cases_by_probe,
            evidence,
        )
        writes = _enhanced_writes(enhanced, cases_by_probe)
        persisted = await self._runs.replace_prepared_clusters(run.id, writes)
        fingerprint = cluster_hash(
            tuple(
                ClusterDraft(
                    type=cluster.type,
                    description=cluster.description,
                    probes=cluster.probes,
                )
                for cluster in enhanced.clusters
            ),
        )
        return _ClusterBuild(
            clusters=persisted,
            fingerprint=fingerprint,
            algorithm=ATTRIBUTION_HYBRID_ALGORITHM,
            draft_count=len(drafts),
            severity_comparison=tuple(
                _severity_comparison(cluster) for cluster in enhanced.clusters
            ),
            degraded=tuple(item.task for item in enhanced.degraded),
        )

    async def _enhance_clusters(
        self,
        run: EvolutionRunRecord,
        agent: AIAgentProvider,
        drafts: Sequence[ClusterDraft],
        cases_by_probe: Mapping[str, set[str]],
        evidence: Mapping[str, BadCaseEvidenceRecord],
    ) -> EnhancedClusters:
        """Run review and scoring over the attribution drafts and record every call.

        The deterministic statistics are gathered here, after the drafts exist,
        so the prompts can receive counts and time spans instead of the member
        lists. Titles no longer feed ``signature_overlap``: the attribution
        conclusion is the grouping signal.
        """
        samples = {
            case_id: ClusterCaseEvidence(
                case_id=case_id,
                title=record.title,
                text=record.description,
                reported_at=record.created_at,
            )
            for case_id, record in evidence.items()
        }
        stats_by_draft: dict[int, ClusterDraftStats] = {}
        for index, draft in enumerate(drafts):
            case_ids = tuple(
                sorted(
                    {
                        case_id
                        for probe_id in draft.probes
                        for case_id in cases_by_probe.get(probe_id, set())
                    },
                ),
            )
            stats_by_draft[index] = ClusterDraftStats(
                case_ids=case_ids,
                time_span_days=_time_span_days(case_ids, evidence),
            )

        async def record_call(call: CallRecord) -> None:
            await self._record(
                run.id,
                "ai_agent_call",
                stage="cluster",
                step_index=4,
                message=f"AI 调用：{call.task}（{call.outcome}）",  # noqa: RUF001
                payload=AiAgentCall(
                    task=call.task,
                    provider=call.provider_id,
                    model=call.model,
                    input_tokens=call.input_tokens,
                    output_tokens=call.output_tokens,
                    cost_usd=call.cost_usd,
                    latency_ms=call.latency_ms,
                    outcome=call.outcome,
                    session_id=call.session_id,
                    trace=call.trace,
                ).payload(),
            )

        async def record_degraded(item: DegradedCall) -> None:
            await self._record(
                run.id,
                "degraded",
                stage="cluster",
                step_index=4,
                message=f"聚类降级：{item.task}",  # noqa: RUF001
                payload={"task": item.task, "reason": item.reason},
                level="warn",
            )

        return await enhance_clusters(
            agent,
            drafts,
            samples,
            stats_by_draft=stats_by_draft,
            record_call=record_call,
            record_degraded=record_degraded,
            failure_policy=self._failure_policy,
            grouping="attribution",
        )

    async def _prepare_workspace(
        self,
        run: EvolutionRunRecord,
        job: JobRunRecord,
    ) -> PreparedWorkspace:
        """Prepare the isolated git workspace, mapping failures to blocked/failed."""
        collector: GitOperationCollector | None = None
        try:
            with git_operation_scope(
                run_id=run.id,
                job_id=job.id,
                stage="prepare",
                target_host=_repo_host(run.repo_url),
            ) as scope:
                collector = scope
                workspace = await self._prepare_workspace_with_checkpoint(run)
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
                    detail=exc.detail,
                ) from None
            raise
        operations: list[dict[str, object]] = []
        truncated = False
        proxy_state = "disabled"
        if collector is not None:
            operations, truncated = collector.bounded()
            proxy_state = collector.proxy_state
        await self._record(
            run.id,
            "workspace_prepared",
            stage="prepare",
            message="隔离 workspace 与 run 分支已准备",
            job_id=job.id,
            payload={
                "baseCommit": workspace.base_commit,
                "branch": workspace.branch,
                "ref": workspace.ref,
                "cacheHit": workspace.cache_hit,
                "cloneSeconds": round(workspace.clone_seconds, 3),
                "proxyState": proxy_state,
                "gitOperations": operations,
                "gitOperationsTruncated": truncated,
            },
        )
        return workspace

    async def _prepare_workspace_with_checkpoint(
        self,
        run: EvolutionRunRecord,
    ) -> PreparedWorkspace:
        """Use the checkpoint-capable preparer when the bound manager offers it."""
        prepare_with_checkpoint = getattr(self._workspaces, "prepare_with_checkpoint", None)
        if not callable(prepare_with_checkpoint):
            return await self._workspaces.prepare(run)

        async def persist(workspace: PreparedWorkspace) -> None:
            await self._runs.write_workspace_checkpoint(
                run.id,
                repo_path=str(workspace.repo_path),
                base_ref=workspace.ref,
                base_commit=workspace.base_commit,
                branch_name=workspace.branch,
                workspace_path=str(workspace.path),
                push_repo_url=workspace.push_url or "",
            )
            await checkpoint(self._runs, run.id)

        return cast(PreparedWorkspace, await prepare_with_checkpoint(run, checkpoint=persist))

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

    async def _attributed_count(self, run: EvolutionRunRecord) -> int:
        """Count distinct included bad cases with an attributed conclusion."""
        rows = await self._attributions.list_clusterable_probes(run.id)
        return len({row.bad_case_id for row in rows})

    async def _category_counts(self, run: EvolutionRunRecord) -> dict[str, int]:
        """Count attributed probes by their closed category."""
        rows = await self._attributions.list_clusterable_probes(run.id)
        counts = dict.fromkeys(TYPE_CONFIDENCE, 0)
        for row in rows:
            if row.attribute_type in counts:
                counts[row.attribute_type] += 1
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
        level: EvolutionRunEventLevel = "info",
    ) -> None:
        """Record one best-effort phase event without masking domain work."""
        if self._events is None:
            return
        try:
            await self._events.record(
                run_id,
                event_type,
                level=level,
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
            source_evidence={
                "kind": case.source_kind,
                "name": case.object_name,
                "type": case.bad_case_type,
                "matches": list(case.matched_sources),
            },
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
        "custom_source": 0,
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
                "custom_source",
                "self_report",
                "after_object",
                "both",
                "policy_excluded",
                "order_unknown",
            )
        },
    }


def _lexical_writes(
    drafts: Sequence[ClusterDraft],
    cases_by_probe: Mapping[str, set[str]],
) -> tuple[ClusterWrite, ...]:
    """Score lexical drafts with the documented constants (legacy path)."""
    scored: list[tuple[float, int, ClusterWrite]] = []
    for draft in drafts:
        case_count = _member_case_count(draft.probes, cases_by_probe)
        scored.append(
            (
                cluster_severity(draft.type, case_count),
                case_count,
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
    return tuple(
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


def _enhanced_writes(
    enhanced: EnhancedClusters,
    cases_by_probe: Mapping[str, set[str]],
) -> tuple[ClusterWrite, ...]:
    """Persist enhanced values, ranked by decision severity then member count then type."""
    scored: list[tuple[float, int, EnhancedCluster]] = [
        (
            cluster.severity,
            _member_case_count(cluster.probes, cases_by_probe),
            cluster,
        )
        for cluster in enhanced.clusters
    ]
    ordered = sorted(scored, key=lambda item: (-item[0], -item[1], item[2].type))
    return tuple(
        ClusterWrite(
            type=cluster.type,
            description=cluster.description,
            probes=cluster.probes,
            impact=cluster.impact,
            confidence=cluster.confidence,
            severity=cluster.severity,
            rank=rank,
        )
        for rank, (_, _, cluster) in enumerate(ordered, start=1)
    )


def _member_case_count(
    probes: Sequence[str],
    cases_by_probe: Mapping[str, set[str]],
) -> int:
    """Count the distinct bad cases behind one cluster's probes."""
    return len(
        {case_id for probe_id in probes for case_id in cases_by_probe.get(probe_id, set())},
    )


def _time_span_days(
    case_ids: Sequence[str],
    evidence: Mapping[str, BadCaseEvidenceRecord],
) -> int | None:
    """Return the reported time span of one draft, or None without two timestamps."""
    timestamps = [evidence[case_id].created_at for case_id in case_ids if case_id in evidence]
    if len(timestamps) < 2:
        return None
    return (max(timestamps) - min(timestamps)).days


def _severity_comparison(cluster: EnhancedCluster) -> dict[str, Any]:
    """Return one formula-versus-decision severity row for the clusters payload.

    The ``clusters_created`` payload is the chosen home: ``severityFormula`` is
    the deterministic formula score kept for metrics even when the LLM severity
    succeeded, and ``severity`` is the value persisted in
    ``probe_clusters.severity``. ``dimensions`` and ``vector`` are audit-only
    facts of the grading, so they stay in the payload while the DB columns keep
    the ``confidence / severity / rank`` contract (06 §5.3, zero migration).
    """
    return {
        "clusterHash": cluster_hash(
            (
                ClusterDraft(
                    type=cluster.type,
                    description=cluster.description,
                    probes=cluster.probes,
                ),
            ),
        ),
        "severityFormula": cluster.formula_severity,
        "severity": cluster.severity,
        "dimensions": dict(cluster.dimensions),
        "vector": cluster.vector,
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


def _repo_host(repo_url: str) -> str | None:
    """Return only the target repository host for observability, never the URL."""
    try:
        parsed = urlsplit(repo_url)
    except ValueError:
        return None
    return parsed.hostname or None


__all__ = ["EvolutionPrepareService"]
