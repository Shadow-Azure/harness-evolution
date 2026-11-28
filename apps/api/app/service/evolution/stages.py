"""Seven-step read-only projection owned by the backend (05 §3.6, 07 §5.10).

One shared ``build_step_payload`` assembles each step DTO from persisted facts.
V2 runs read candidates, attributions, clusters, and rounds; historical V1 runs
are mapped from their probe rows into the same seven-step shapes, so the client
never needs a second step schema.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any, Literal, cast

from pydantic import Field

from app.db.crud.attributions import AttributionRecord, EvolutionRunCandidateRepository
from app.db.crud.bad_cases import BadCaseRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.probe_query import ProbeHitRow, ProbeQueryRepository
from app.db.models.evolution import (
    EvolutionRoundRecord,
    EvolutionRunCandidateRecord,
    EvolutionRunRecord,
    ProbeClusterRecord,
)
from app.errors import AppError, ErrorCode
from app.service.evolution.attribution_contracts import AttributionConclusion
from app.service.evolution.patch_source import PatchBundle
from app.service.evolution.potential import (
    AnchorSource,
    HitReason,
    OrderState,
    PotentialReasonCounts,
)
from app.service.evolution.round_patch import stored_bundle
from app.service.evolution.state import (
    STEP_KEYS,
    STEP_TITLES,
    StepNotReady,
    ensure_step_readable,
    is_legacy_run,
    step_states,
)
from app.service.identity.schemas import IdentityModel

StepKey = Literal[
    "range",
    "sessions",
    "potential",
    "attribution",
    "clusters",
    "iteration",
    "final",
]
StepStatus = Literal["done", "active", "pending"]
ClusterType = Literal["model", "prompt", "error", "flow", "context"]
RoundStatus = Literal[
    "pending",
    "patching",
    "pushing",
    "evaluating",
    "deciding",
    "accepted",
    "rejected",
    "skipped",
    "failed",
]
RoundPushStatus = Literal["pending", "pushing", "succeeded", "skipped", "failed"]
RoundEvalStatus = Literal["pending", "evaluating", "completed", "failed", "timeout"]
AttributionSource = Literal["cached", "fresh"]
_CLUSTER_TYPES: tuple[str, ...] = ("model", "prompt", "error", "flow", "context")
SESSIONS_PAGE_SIZE = 4
_SESSION_SHORT_TITLE_LIMIT = 120
POTENTIAL_PAGE_SIZE = 5


class StepRangeTarget(IdentityModel):
    """One member shown by the selection step."""

    object_type: Literal["skill", "agent", "knowledge"]
    object_name: str
    target_version: str
    target_revision: str | None = None
    sub_dir: str = ""


class StepRangeCondition(IdentityModel):
    """Immutable selection snapshot shown on step 1."""

    target_type: Literal["skill", "agent", "knowledge"]
    target_name: str
    target_version: str
    target_revision: str | None = Field(
        default=None,
        description=(
            "Resolved file-matching revision (digest:<sha256(body)>); null on "
            "historical runs that were created before content resolution."
        ),
    )
    targets: list[StepRangeTarget] = Field(default_factory=list)
    window_from: date | None = Field(default=None, alias="from")
    window_to: date | None = Field(default=None, alias="to")
    policy: dict[str, Any]
    cache_enabled: bool
    attribution_package_id: str | None = None
    workspace_id: str


class StepRangeStats(IdentityModel):
    """Headline counts of the selection step."""

    sessions: int = 0
    bad_cases: int = 0
    potential: int = 0


class StepRangePayload(IdentityModel):
    """Selection condition plus its headline statistics."""

    condition: StepRangeCondition
    stats: StepRangeStats


class StepSessionsSummary(IdentityModel):
    """Non-overlapping Session partition of step 2."""

    reported: int = 0
    associated: int = 0
    skipped: int = 0
    version_unresolved: int = 0
    pending: int = 0


class StepSessionRow(IdentityModel):
    """One associated Session row of step 2."""

    session_id: str
    title: str | None
    short: str | None = None
    object_trigger_at: datetime | None
    bad_case_count: int = 0
    potential_count: int = 0
    members: list[str] = Field(default_factory=list)


class StepSessionsPayload(IdentityModel):
    """Paged associated Session projection."""

    summary: StepSessionsSummary
    rows: list[StepSessionRow]
    total: int = 0
    page: int = 1
    page_size: int = SESSIONS_PAGE_SIZE


class StepPotentialSummary(IdentityModel):
    """Evaluated and included cases with the closed reason distribution."""

    bad_cases: int = 0
    potential: int = 0
    by_reason: PotentialReasonCounts


class StepPotentialRow(IdentityModel):
    """One included bad case row of step 3."""

    bad_case_id: str
    object_name: str
    bad_case_type: str
    trigger_at: datetime | None
    session_id: str
    hit_reason: HitReason
    order_state: OrderState
    anchor_source: AnchorSource


class StepPotentialPayload(IdentityModel):
    """Paged potential rows; excluded rows stay in the summary only."""

    summary: StepPotentialSummary
    rows: list[StepPotentialRow]
    total: int = 0
    page: int = 1
    page_size: int = POTENTIAL_PAGE_SIZE


class StepAttributionSummary(IdentityModel):
    """Four counts of the attribution step."""

    potential: int = 0
    reused: int = 0
    fresh: int = 0
    non_target: int = 0


class StepAttributionRow(IdentityModel):
    """One case attribution conclusion of step 4.

    ``session_id`` is the source Session that owns the bad case. The client
    needs it to build the canonical error-detail deep link without a second
    lookup; rows without a Session cannot offer that link.
    """

    bad_case_id: str
    session_id: str
    attribution_id: str
    category: ClusterType | None
    conclusion: AttributionConclusion | None = None
    description: str
    source: AttributionSource
    confidence: float | None


class StepAttributionPayload(IdentityModel):
    """Attribution summary plus one row per included case."""

    summary: StepAttributionSummary
    rows: list[StepAttributionRow]


class StepClusterCase(IdentityModel):
    """One source bad case inside a cluster."""

    bad_case_id: str
    title: str
    object_name: str
    bad_case_type: str
    trigger_at: datetime | None
    created_at: datetime | None


class StepCluster(IdentityModel):
    """One ranked cluster with its source cases and stored scores."""

    cluster_id: str
    title: str
    description: str
    category: ClusterType
    case_count: int
    confidence: float | None
    severity: float | None
    rank: int | None
    cases: list[StepClusterCase]


class StepClustersPayload(IdentityModel):
    """Clusters ordered by severity descending plus the AI-mode audit facts.

    ``degraded`` lists the task keys a ``degrade`` policy replaced with
    deterministic fallbacks, so a degraded result is never presented as model
    participation. ``failure`` carries the sanitized run error when a strict
    policy failed the run at this step.
    """

    clusters: list[StepCluster]
    algorithm: str | None = None
    failure_policy: Literal["strict", "degrade"] | None = None
    degraded: list[str] = Field(default_factory=list)
    failure: str | None = None


class StepCandidate(IdentityModel):
    """Pushed candidate ref backing one evaluation round."""

    ref: str
    commit: str
    message: str


class StepRoundFilePatch(IdentityModel):
    """One file inside a round's patch preview."""

    file: str
    lines: list[str]
    overwrite: bool = False


class StepRoundPatch(IdentityModel):
    """Patch preview projected from the round's stored bundle.

    The durable shape carries ``files[]`` plus ``note``/``diff``/``intent``/
    ``report``, and single-file rounds also keep the legacy ``file``/``lines``
    keys. This read model is built from :func:`stored_bundle` instead of
    validating the raw dictionary, so a later writer field cannot break step 6
    again.

    ``diff`` is the candidate commit's unified diff, already split into lines.
    New rounds persist it; historical rounds that lack it get a change-block
    diff synthesized from the applied ``intent``/``report`` pair, and ``None``
    means no diff can be produced, so the client must show the neutral
    whole-file preview instead of classifying lines.
    """

    files: list[StepRoundFilePatch]
    note: str | None = None
    diff: list[str] | None = None


class StepRoundPush(IdentityModel):
    """Candidate push outcome stored on the round."""

    status: RoundPushStatus
    attempts: int
    error: str | None


class StepRoundEval(IdentityModel):
    """External evaluation state stored on the round."""

    status: RoundEvalStatus
    current: float | None
    candidate: float | None
    next_poll_at: datetime | None = None


class StepFinalCommit(IdentityModel):
    """Amended run-branch commit produced when a round was accepted."""

    hash: str
    message: str


class StepRound(IdentityModel):
    """One execution round rendered by the iteration step."""

    round_id: str
    cluster_id: str
    title: str
    category: ClusterType
    case_count: int
    confidence: float | None
    severity: float | None
    cases: list[StepClusterCase]
    status: RoundStatus
    candidate: StepCandidate | None
    patch: StepRoundPatch | None
    push: StepRoundPush
    eval: StepRoundEval
    accepted: bool
    final_commit: StepFinalCommit | None = None


class StepIterationPayload(IdentityModel):
    """Rounds of step 6 in sequence order."""

    rounds: list[StepRound]


class StepFinalChange(IdentityModel):
    """One accepted round inside the terminal modification list."""

    commit: str
    cluster_id: str
    title: str
    category: ClusterType
    report_count: int


class StepFinalPayload(IdentityModel):
    """Terminal evaluation verdict with metrics and accepted changes.

    The four verdict fields stay null until `evolution_finals` has a row, so an
    active final step cannot be mistaken for a failing verdict.
    """

    verdict: bool | None
    best_version: str | None
    best_score: float | None
    init_score: float | None
    metrics: list[dict[str, Any]]
    changes: list[StepFinalChange]
    degraded: bool = False


class EvolutionStepShell(IdentityModel):
    """Envelope fields shared by the seven step endpoints."""

    index: int
    title: str
    status: StepStatus
    clickable: bool
    detail: str | None = None


class EvolutionStepRange(EvolutionStepShell):
    """Step 0 response: selection snapshot and headline counts."""

    key: Literal["range"] = "range"
    payload: StepRangePayload


class EvolutionStepSessions(EvolutionStepShell):
    """Step 1 response: paged Session association."""

    key: Literal["sessions"] = "sessions"
    payload: StepSessionsPayload


class EvolutionStepPotential(EvolutionStepShell):
    """Step 2 response: paged potential bad cases."""

    key: Literal["potential"] = "potential"
    payload: StepPotentialPayload


class EvolutionStepAttribution(EvolutionStepShell):
    """Step 3 response: per-case attribution conclusions."""

    key: Literal["attribution"] = "attribution"
    payload: StepAttributionPayload


class EvolutionStepClusters(EvolutionStepShell):
    """Step 4 response: ranked clusters with source cases."""

    key: Literal["clusters"] = "clusters"
    payload: StepClustersPayload


class EvolutionStepIteration(EvolutionStepShell):
    """Step 5 response: iteration rounds."""

    key: Literal["iteration"] = "iteration"
    payload: StepIterationPayload


class EvolutionStepFinal(EvolutionStepShell):
    """Step 6 response: terminal evaluation."""

    key: Literal["final"] = "final"
    payload: StepFinalPayload


EvolutionStep = (
    EvolutionStepRange
    | EvolutionStepSessions
    | EvolutionStepPotential
    | EvolutionStepAttribution
    | EvolutionStepClusters
    | EvolutionStepIteration
    | EvolutionStepFinal
)


class _RunFacts:
    """Facts loaded once per payload build and shared by the step builders."""

    def __init__(
        self,
        run: EvolutionRunRecord,
        clusters: Sequence[ProbeClusterRecord],
        candidates: Sequence[EvolutionRunCandidateRecord],
        attributions: Sequence[AttributionRecord],
        probes: Sequence[ProbeHitRow],
        case_titles: Mapping[str, str],
        cluster_links: dict[str, tuple[str, ...]],
    ) -> None:
        """Store the run and its candidate/attribution/probe/title snapshot."""
        self.run = run
        self.clusters = clusters
        self.candidates = candidates
        self.attributions = attributions
        self.probes = probes
        self.case_titles = case_titles
        self.cluster_links = cluster_links
        self.legacy = is_legacy_run(run.attribution_engine)

    @property
    def attribution_by_case(self) -> dict[str, AttributionRecord]:
        """Return one primary attribution per case."""
        found: dict[str, AttributionRecord] = {}
        for record in self.attributions:
            found.setdefault(record.bad_case_id, record)
        return found

    @property
    def probes_by_id(self) -> dict[str, list[ProbeHitRow]]:
        """Group legacy probe rows by probe id."""
        grouped: dict[str, list[ProbeHitRow]] = OrderedDict()
        for row in self.probes:
            grouped.setdefault(row.probe_id, []).append(row)
        return grouped

    @property
    def case_rows(self) -> dict[str, list[ProbeHitRow]]:
        """Group legacy probe rows by source bad case."""
        grouped: dict[str, list[ProbeHitRow]] = OrderedDict()
        for row in self.probes:
            grouped.setdefault(row.bad_case_id, []).append(row)
        return grouped


class EvolutionStageService:
    """Project one run's persisted facts through shared readiness rules."""

    def __init__(
        self,
        runs: EvolutionRepository,
        probes: ProbeQueryRepository,
        candidates: EvolutionRunCandidateRepository,
        attributions: Any,
        bad_cases: BadCaseRepository,
    ) -> None:
        """Bind the run, probe, candidate, attribution, and bad-case readers."""
        self._runs = runs
        self._probes = probes
        self._candidates = candidates
        self._attributions = attributions
        self._bad_cases = bad_cases

    async def step(
        self,
        run_id: str,
        key: StepKey,
        *,
        workspace_ids: Sequence[str] | None = None,
        page: int = 1,
        page_size: int | None = None,
    ) -> EvolutionStep:
        """Return one readable step or fail with the documented 404 codes."""
        run = await self._runs.get_run(run_id, workspace_ids=workspace_ids)
        if run is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.RUN_NOT_FOUND,
                message="evolution run not found",
            )
        clusters = await self._runs.list_clusters(run_id)
        try:
            ensure_step_readable(
                run.progress_unit,
                len(clusters),
                run.status,
                key,
                run.mode,
                attribution_engine=run.attribution_engine,
                error_stage=run.error_stage,
            )
        except StepNotReady as exc:
            raise AppError(
                status_code=404,
                code=ErrorCode.STEP_NOT_READY,
                message="requested evolution step has not been reached",
                details={"key": key},
            ) from exc
        facts = await self._facts(run, clusters)
        return await self.build_step_payload(facts, key, page=page, page_size=page_size)

    async def _facts(
        self,
        run: EvolutionRunRecord,
        clusters: Sequence[ProbeClusterRecord],
    ) -> _RunFacts:
        """Load the candidate, attribution, legacy probe, and case-title snapshot."""
        candidates = await self._candidates.list(run.id)
        attributions = await self._attributions.list_run_attributions(run.id) if candidates else ()
        links = await self._runs.list_cluster_probes(run.id)
        if candidates:
            probes: Sequence[ProbeHitRow] = ()
            case_ids = tuple(dict.fromkeys(candidate.bad_case_id for candidate in candidates))
        else:
            probe_ids = tuple(dict.fromkeys(link.probe_id for link in links))
            probes = await self._probes.list_rows_by_ids(probe_ids) if probe_ids else ()
            case_ids = tuple(dict.fromkeys(row.bad_case_id for row in probes))
        case_titles = await self._bad_cases.titles_by_ids(case_ids)
        cluster_links: dict[str, tuple[str, ...]] = {}
        for link in links:
            cluster_links.setdefault(link.probe_cluster_id, ())
            cluster_links[link.probe_cluster_id] = (
                *cluster_links[link.probe_cluster_id],
                link.probe_id,
            )
        return _RunFacts(
            run,
            clusters,
            candidates,
            attributions,
            probes,
            case_titles,
            cluster_links,
        )

    async def build_step_payload(
        self,
        facts: _RunFacts,
        key: StepKey,
        *,
        page: int = 1,
        page_size: int | None = None,
    ) -> EvolutionStep:
        """Assemble one step DTO from persisted facts without recomputing facts.

        Args:
            facts: Run snapshot with candidates, attributions, and probes.
            key: Requested step key inside the closed seven-key vocabulary.
            page: One-based page for the paged steps.
            page_size: Optional page size; defaults to the documented size.

        Returns:
            The key-discriminated step envelope with its payload.
        """
        size = page_size or (SESSIONS_PAGE_SIZE if key == "sessions" else POTENTIAL_PAGE_SIZE)
        builders: dict[StepKey, Callable[[], Awaitable[EvolutionStep]]] = {
            "range": lambda: self._range(facts),
            "sessions": lambda: self._sessions(facts, page, size),
            "potential": lambda: self._potential(facts, page, size),
            "attribution": lambda: self._attribution(facts),
            "clusters": lambda: self._clusters(facts),
            "iteration": lambda: self._iteration(facts),
            "final": lambda: self._final(facts),
        }
        return await builders[key]()

    def _shell(
        self,
        facts: _RunFacts,
        key: StepKey,
        *,
        detail: str | None = None,
    ) -> dict[str, Any]:
        """Return the shared envelope fields from the seven-step state machine."""
        run = facts.run
        index = STEP_KEYS.index(key)
        state = step_states(
            run.progress_unit,
            len(facts.clusters),
            run.status,
            attribution_engine=run.attribution_engine,
            error_stage=run.error_stage,
        )[index]
        return {
            "index": index,
            "title": STEP_TITLES[index],
            "status": state.status,
            "clickable": state.clickable,
            "detail": detail,
        }

    async def _range(self, facts: _RunFacts) -> EvolutionStepRange:
        """Assemble the selection snapshot and headline counts."""
        run = facts.run
        stats = StepRangeStats(
            sessions=_int_stat(run.stats, "sessions"),
            bad_cases=_int_stat(run.stats, "badCases"),
            potential=_int_stat(run.stats, "potential"),
        )
        if facts.legacy:
            stats = StepRangeStats(
                sessions=_int_stat(run.stats, "sessions"),
                bad_cases=_int_stat(run.stats, "probes"),
                potential=_int_stat(run.stats, "usedProbes"),
            )
        policy = dict(run.potential_policy or {"preset": "default"})
        package_id = policy.pop("attributionPackageId", None)
        policy.pop("latestReportsOnly", None)
        policy.pop("legacyRule", None)
        return EvolutionStepRange(
            **self._shell(facts, "range", detail=f"{stats.bad_cases} 个 bad case"),
            payload=StepRangePayload(
                condition=StepRangeCondition.model_validate(
                    {
                        "targetType": run.target_type,
                        "targetName": run.target_name,
                        "targetVersion": run.target_version,
                        "targetRevision": run.target_revision,
                        "targets": [
                            {
                                "objectType": item.object_type,
                                "objectName": item.object_name,
                                "targetVersion": item.target_version,
                                "targetRevision": item.target_revision,
                                "subDir": item.sub_dir,
                            }
                            for item in run.targets
                        ],
                        "from": run.window_from,
                        "to": run.window_to,
                        "policy": policy,
                        "attributionPackageId": package_id,
                        "cacheEnabled": run.cache_enabled,
                        "workspaceId": run.workspace_id,
                    },
                ),
                stats=stats,
            ),
        )

    async def _sessions(self, facts: _RunFacts, page: int, size: int) -> EvolutionStepSessions:
        """Assemble the paged associated-Session projection."""
        rows = _legacy_session_rows(facts) if facts.legacy else _v2_session_rows(facts)
        total = len(rows)
        shown = rows[(page - 1) * size : page * size]
        summary = _session_summary(facts, total)
        return EvolutionStepSessions(
            **self._shell(facts, "sessions", detail=f"{total} 个 Session"),
            payload=StepSessionsPayload(
                summary=summary,
                rows=shown,
                total=total,
                page=page,
                page_size=size,
            ),
        )

    async def _potential(
        self,
        facts: _RunFacts,
        page: int,
        size: int,
    ) -> EvolutionStepPotential:
        """Assemble the paged potential bad-case projection."""
        rows = _legacy_potential_rows(facts) if facts.legacy else _v2_potential_rows(facts)
        total = len(rows)
        shown = rows[(page - 1) * size : page * size]
        summary = _potential_summary(facts, total)
        return EvolutionStepPotential(
            **self._shell(facts, "potential", detail=f"{total} / {summary.bad_cases}"),
            payload=StepPotentialPayload(
                summary=summary,
                rows=shown,
                total=total,
                page=page,
                page_size=size,
            ),
        )

    async def _attribution(self, facts: _RunFacts) -> EvolutionStepAttribution:
        """Assemble per-case attribution conclusions and their counts."""
        rows = _legacy_attribution_rows(facts) if facts.legacy else _v2_attribution_rows(facts)
        potential = len(rows) if facts.legacy else sum(case.included for case in facts.candidates)
        reused = sum(1 for row in rows if row.source == "cached")
        non_target = sum(
            row.category is None if facts.legacy else row.conclusion == "non_target" for row in rows
        )
        return EvolutionStepAttribution(
            **self._shell(facts, "attribution", detail=f"{len(rows)} 条"),
            payload=StepAttributionPayload(
                summary=StepAttributionSummary(
                    potential=potential,
                    reused=reused,
                    fresh=len(rows) - reused,
                    non_target=non_target,
                ),
                rows=rows,
            ),
        )

    async def _clusters(self, facts: _RunFacts) -> EvolutionStepClusters:
        """Assemble severity-ordered clusters with their source cases."""
        clusters = sorted(
            facts.clusters,
            key=lambda cluster: (
                cluster.severity is None,
                -(cluster.severity or 0.0),
                cluster.rank if cluster.rank is not None else 1_000,
                cluster.seq,
            ),
        )
        stats = facts.run.stats
        algorithm = stats.get("clusterAlgorithm")
        policy = stats.get("clusterFailurePolicy")
        degraded_raw = stats.get("clusterDegraded")
        failure = (
            facts.run.error_message
            if facts.run.status == "failed" and facts.run.error_stage == "cluster"
            else None
        )
        return EvolutionStepClusters(
            **self._shell(facts, "clusters", detail=f"{len(clusters)} 簇"),
            payload=StepClustersPayload(
                clusters=[_cluster_item(facts, cluster) for cluster in clusters],
                algorithm=algorithm if isinstance(algorithm, str) else None,
                failure_policy=(
                    cast(Literal["strict", "degrade"], policy)
                    if policy in ("strict", "degrade")
                    else None
                ),
                degraded=(
                    [str(item) for item in degraded_raw] if isinstance(degraded_raw, list) else []
                ),
                failure=failure,
            ),
        )

    async def _iteration(self, facts: _RunFacts) -> EvolutionStepIteration:
        """Assemble the persisted execution rounds."""
        rounds = list(await self._runs.list_rounds(facts.run.id))
        cluster_by_id = {cluster.probe_cluster_id: cluster for cluster in facts.clusters}
        return EvolutionStepIteration(
            **self._shell(facts, "iteration"),
            payload=StepIterationPayload(
                rounds=[
                    _round_item(facts, round_, cluster_by_id.get(round_.probe_cluster_id))
                    for round_ in rounds
                ],
            ),
        )

    async def _final(self, facts: _RunFacts) -> EvolutionStepFinal:
        """Assemble the terminal evaluation and accepted changes."""
        final = await self._runs.get_final(facts.run.id)
        rounds = list(await self._runs.list_rounds(facts.run.id))
        cluster_by_id = {cluster.probe_cluster_id: cluster for cluster in facts.clusters}
        changes = [
            StepFinalChange(
                commit=round_.commit_hash or "",
                cluster_id=round_.probe_cluster_id,
                title=(
                    cluster_by_id[round_.probe_cluster_id].probe_cluster_description
                    if round_.probe_cluster_id in cluster_by_id
                    else ""
                ),
                category=(
                    cluster_by_id[round_.probe_cluster_id].probe_cluster_type
                    if round_.probe_cluster_id in cluster_by_id
                    else "error"
                ),
                report_count=len(
                    _cluster_cases(facts, round_.probe_cluster_id),
                ),
            )
            for round_ in rounds
            if round_.accepted and round_.commit_hash is not None
        ]
        return EvolutionStepFinal(
            **self._shell(facts, "final"),
            payload=StepFinalPayload(
                verdict=final.verdict if final is not None else None,
                best_version=final.best_version if final is not None else None,
                best_score=final.best_score if final is not None else None,
                init_score=final.init_score if final is not None else None,
                metrics=final.metrics if final is not None else [],
                changes=changes,
                degraded=_has_degraded_clusters(facts.run.stats),
            ),
        )


def _has_degraded_clusters(stats: Mapping[str, Any]) -> bool:
    """Return whether the cluster step recorded any deterministic fallback."""
    value = stats.get("clusterDegraded")
    return isinstance(value, list) and any(isinstance(item, str) for item in value)


def _int_stat(stats: Mapping[str, Any], key: str) -> int:
    """Read one non-negative integer from a persisted stats mapping."""
    value = stats.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _potential_summary(facts: _RunFacts, total: int) -> StepPotentialSummary:
    """Return the persisted potential summary for either schema."""
    raw = facts.run.stats
    if facts.legacy:
        return StepPotentialSummary(
            bad_cases=_int_stat(raw, "probes"),
            potential=total,
            by_reason=PotentialReasonCounts(
                self_report=total,
            ),
        )
    by_reason_raw = raw.get("byReason")
    by_reason = by_reason_raw if isinstance(by_reason_raw, Mapping) else {}
    return StepPotentialSummary(
        bad_cases=_int_stat(raw, "badCases"),
        potential=_int_stat(raw, "potential") or total,
        by_reason=PotentialReasonCounts(
            self_report=_int_stat(by_reason, "self_report"),
            custom_source=_int_stat(by_reason, "custom_source"),
            after_object=_int_stat(by_reason, "after_object"),
            both=_int_stat(by_reason, "both"),
            policy_excluded=_int_stat(by_reason, "policy_excluded"),
            order_unknown=_int_stat(by_reason, "order_unknown"),
        ),
    )


def _session_summary(facts: _RunFacts, total: int) -> StepSessionsSummary:
    """Return the persisted non-overlapping session partition."""
    raw = facts.run.stats
    if facts.legacy:
        return StepSessionsSummary(associated=total, reported=total)
    return StepSessionsSummary(
        reported=_int_stat(raw, "reportedSessions") or total,
        associated=_int_stat(raw, "sessions") or total,
        skipped=_int_stat(raw, "skippedSessions"),
        version_unresolved=_int_stat(raw, "versionUnresolvedSessions"),
        pending=_int_stat(raw, "pendingSessions"),
    )


def _short_label(title: str | None) -> str | None:
    """Bound the prompt-derived title used as the step-2 Session label."""
    return title[:_SESSION_SHORT_TITLE_LIMIT] if title else None


def _v2_session_rows(facts: _RunFacts) -> list[StepSessionRow]:
    """Read the persisted Session snapshot, falling back to candidate rows."""
    raw = facts.run.stats.get("sessionRows")
    if isinstance(raw, list):
        persisted: list[StepSessionRow] = []
        for item in raw:
            if not isinstance(item, Mapping) or not isinstance(item.get("sessionId"), str):
                continue
            trigger = item.get("objectTriggerAt")
            title = item.get("title") if isinstance(item.get("title"), str) else None
            short = item.get("short") if isinstance(item.get("short"), str) else None
            persisted.append(
                StepSessionRow(
                    session_id=str(item["sessionId"]),
                    title=title,
                    short=short or _short_label(title),
                    object_trigger_at=(
                        datetime.fromisoformat(trigger) if isinstance(trigger, str) else None
                    ),
                    bad_case_count=_int_stat(item, "badCaseCount"),
                    potential_count=_int_stat(item, "potentialCount"),
                    members=[
                        str(member) for member in item.get("members", []) if isinstance(member, str)
                    ]
                    if isinstance(item.get("members"), list)
                    else [],
                ),
            )
        if persisted:
            return persisted
    grouped: dict[str, list[EvolutionRunCandidateRecord]] = OrderedDict()
    for candidate in facts.candidates:
        grouped.setdefault(candidate.session_id, []).append(candidate)
    rows: list[StepSessionRow] = []
    for session_id, candidates in grouped.items():
        trigger = next(
            (
                candidate.object_trigger_at
                for candidate in candidates
                if candidate.object_trigger_at is not None
            ),
            None,
        )
        rows.append(
            StepSessionRow(
                session_id=session_id,
                title=None,
                object_trigger_at=trigger,
                bad_case_count=len({candidate.bad_case_id for candidate in candidates}),
                potential_count=len(
                    {candidate.bad_case_id for candidate in candidates if candidate.included},
                ),
                members=list(
                    dict.fromkeys(
                        candidate.object_name or facts.run.target_name for candidate in candidates
                    ),
                ),
            ),
        )
    return rows


def _legacy_session_rows(facts: _RunFacts) -> list[StepSessionRow]:
    """Map legacy probe rows to one synthetic Session row each."""
    grouped: dict[str, list[ProbeHitRow]] = OrderedDict()
    for row in facts.probes:
        grouped.setdefault(row.probe_session_id, []).append(row)
    mapped: list[StepSessionRow] = []
    for session_id, rows in grouped.items():
        title = next((row.session_title for row in rows if row.session_title), None)
        mapped.append(
            StepSessionRow(
                session_id=session_id,
                title=title,
                short=_short_label(title),
                object_trigger_at=next(
                    (row.probe_started_at for row in rows if row.probe_started_at is not None),
                    None,
                ),
                bad_case_count=len({row.bad_case_id for row in rows}),
                potential_count=len({row.bad_case_id for row in rows}),
            ),
        )
    return mapped


def _v2_potential_rows(facts: _RunFacts) -> list[StepPotentialRow]:
    """Map included candidates to step-3 rows."""
    return [
        StepPotentialRow(
            bad_case_id=candidate.bad_case_id,
            object_name=(candidate.source_evidence or {}).get(
                "name", candidate.object_name or facts.run.target_name
            ),
            bad_case_type=(candidate.source_evidence or {}).get(
                "type",
                "self" if candidate.included_reason in {"self_report", "both"} else "discovery",
            ),
            trigger_at=candidate.case_trigger_at,
            session_id=candidate.session_id,
            hit_reason=cast(HitReason, candidate.included_reason),
            order_state=cast(OrderState, candidate.order_state),
            anchor_source=cast(AnchorSource, candidate.case_anchor_kind or "unknown"),
        )
        for candidate in facts.candidates
        if candidate.included
    ]


def _legacy_potential_rows(facts: _RunFacts) -> list[StepPotentialRow]:
    """Map legacy probes to synthetic potential rows without inventing order."""
    rows: list[StepPotentialRow] = []
    for bad_case_id, probe_rows in facts.case_rows.items():
        first = probe_rows[0]
        same_object = first.probe_object == facts.run.target_name
        rows.append(
            StepPotentialRow(
                bad_case_id=bad_case_id,
                object_name=first.probe_object,
                bad_case_type="self" if same_object else "discovery",
                trigger_at=first.probe_started_at,
                session_id=first.probe_session_id,
                hit_reason="self_report" if same_object else "after_object",
                order_state="unknown",
                anchor_source="unknown",
            ),
        )
    return rows


def _v2_attribution_rows(facts: _RunFacts) -> list[StepAttributionRow]:
    """Map candidates and their primary attribution to step-4 rows."""
    primary = facts.attribution_by_case
    rows: list[StepAttributionRow] = []
    for candidate in facts.candidates:
        if not candidate.included or candidate.probe_id is None:
            continue
        record = primary.get(candidate.bad_case_id)
        if record is None:
            continue
        category = (
            cast(ClusterType, record.attribute_type)
            if record.attribute_type in _CLUSTER_TYPES
            else None
        )
        rows.append(
            StepAttributionRow(
                bad_case_id=candidate.bad_case_id,
                session_id=candidate.session_id,
                attribution_id=record.probe_id,
                category=category,
                conclusion=cast(AttributionConclusion, record.conclusion),
                description=record.probe_description,
                source="cached" if candidate.is_cached else "fresh",
                confidence=record.confidence,
            ),
        )
    return rows


def _legacy_attribution_rows(facts: _RunFacts) -> list[StepAttributionRow]:
    """Map legacy probe analyses to attribution rows."""
    rows: list[StepAttributionRow] = []
    for probe_id, probe_rows in facts.probes_by_id.items():
        first = probe_rows[0]
        category = (
            cast(ClusterType, first.attribute_type)
            if first.attribute_type in _CLUSTER_TYPES
            else None
        )
        rows.append(
            StepAttributionRow(
                bad_case_id=first.bad_case_id,
                session_id=first.probe_session_id,
                attribution_id=probe_id,
                category=category,
                description=first.probe_description,
                source="fresh",
                confidence=None,
            ),
        )
    return rows


def _cluster_cases(facts: _RunFacts, cluster_id: str) -> list[StepClusterCase]:
    """Return the source cases behind one cluster for either schema."""
    probe_ids = _cluster_links(facts, cluster_id)
    if facts.legacy:
        seen: dict[str, ProbeHitRow] = {}
        for probe_id in probe_ids:
            for row in facts.probes_by_id.get(probe_id, ()):  # pragma: no branch
                seen.setdefault(row.bad_case_id, row)
        return [
            StepClusterCase(
                bad_case_id=row.bad_case_id,
                title=facts.case_titles.get(row.bad_case_id) or row.bad_case_id,
                object_name=row.probe_object,
                bad_case_type="self" if row.probe_object == facts.run.target_name else "discovery",
                trigger_at=row.probe_started_at,
                created_at=None,
            )
            for row in seen.values()
        ]
    candidates = [
        candidate
        for candidate in facts.candidates
        if candidate.probe_id in set(probe_ids) and candidate.included
    ]
    return [
        StepClusterCase(
            bad_case_id=candidate.bad_case_id,
            title=facts.case_titles.get(candidate.bad_case_id) or candidate.bad_case_id,
            object_name=(candidate.source_evidence or {}).get(
                "name", candidate.object_name or facts.run.target_name
            ),
            bad_case_type=(candidate.source_evidence or {}).get(
                "type",
                "self" if candidate.included_reason in {"self_report", "both"} else "discovery",
            ),
            trigger_at=candidate.case_trigger_at,
            created_at=candidate.created_at,
        )
        for candidate in candidates
    ]


def _cluster_links(facts: _RunFacts, cluster_id: str) -> Sequence[str]:
    """Return the cluster probe links loaded with the cluster snapshot."""
    return facts.cluster_links.get(cluster_id, ())


def _cluster_item(facts: _RunFacts, cluster: ProbeClusterRecord) -> StepCluster:
    """Render one persisted cluster with its cases and stored scores."""
    cases = _cluster_cases(facts, cluster.probe_cluster_id)
    return StepCluster(
        cluster_id=cluster.probe_cluster_id,
        title=_cluster_title(cluster.probe_cluster_description),
        description=cluster.probe_cluster_description,
        category=cluster.probe_cluster_type,
        case_count=len(cases),
        confidence=cluster.confidence,
        severity=cluster.severity,
        rank=cluster.rank,
        cases=cases,
    )


def _cluster_title(description: str) -> str:
    """Render the cluster headline from its root-cause description.

    The stored description is composed as ``{type} 类问题 · {title} · {summary}``
    (the legacy lexical path stores ``{type} 类问题 · {representative title}``).
    The header shows only the root-cause title, so the card does not repeat the
    full description; the expanded section still shows the composed text.
    """
    normalized = " ".join(description.split())
    if not normalized:
        return "聚类问题"
    parts = normalized.split(" · ")
    title = " · ".join(parts[:2]) if len(parts) > 2 else normalized
    if len(title) <= 80:
        return title
    return title[:79].rstrip() + "…"


def _round_patch(raw: object) -> StepRoundPatch | None:
    """Project one stored round patch into the read DTO.

    Only the fields this step exposes are read from the restored bundle; the
    persisted dictionary is never fed to a closed model directly. The client
    renders ``diff`` when it exists and falls back to the neutral whole-file
    preview otherwise.
    """
    bundle = stored_bundle(raw)
    if bundle is None:
        return None
    note = raw.get("note") if isinstance(raw, Mapping) else None
    return StepRoundPatch(
        files=[
            StepRoundFilePatch(
                file=patch.file,
                lines=list(patch.lines),
                overwrite=patch.overwrite,
            )
            for patch in bundle.files
        ],
        note=note if isinstance(note, str) and note.strip() else None,
        diff=_patch_diff(bundle),
    )


def _patch_diff(bundle: PatchBundle) -> list[str] | None:
    """Return the candidate's real diff, falling back to stored edit intent.

    The writer persists the git-produced diff after the candidate commit. A
    round stored before that field existed can still describe what changed
    through ``intent`` + ``report``; synthesizing change blocks from those two
    keeps the page auditable without pretending the whole file is a diff.
    """
    if bundle.unified_diff.strip():
        return bundle.unified_diff.splitlines()
    return _intent_diff(bundle)


def _intent_diff(bundle: PatchBundle) -> list[str] | None:
    """Synthesize a change-block diff from the applied edits of one plan.

    Only edits whose stored report entry is ``applied`` participate, so a
    skipped or failed edit never shows up as a change. Returns ``None`` when
    there is neither a plan nor an applied edit, which keeps the neutral
    preview for legacy rounds that never recorded intent.
    """
    plan = bundle.intent
    if plan is None or not bundle.report:
        return None
    applied = {status.index: status for status in bundle.report if status.status == "applied"}
    lines: list[str] = []
    current_file: str | None = None
    for index, edit in enumerate(plan.edits):
        if index not in applied:
            continue
        if edit.file != current_file:
            current_file = edit.file
            lines.extend(
                (
                    f"diff --git a/{edit.file} b/{edit.file}",
                    f"--- a/{edit.file}",
                    f"+++ b/{edit.file}",
                ),
            )
        lines.append(f"@@ 编辑 {index + 1} · {edit.op} @@")
        target = (edit.target or "").splitlines()
        content = (edit.content or "").splitlines()
        if edit.op in {"replace", "delete"}:
            lines.extend(f"-{line}" for line in target)
        if edit.op == "insert_after":
            # Keep the anchor visible so the inserted lines stay locatable
            # even though the synthesized hunk has no line numbers.
            lines.extend(f" {line}" for line in target)
        if edit.op in {"replace", "insert_after", "append"}:
            lines.extend(f"+{line}" for line in content)
    return lines or None


def _round_item(
    facts: _RunFacts,
    round_: EvolutionRoundRecord,
    cluster: ProbeClusterRecord | None,
) -> StepRound:
    """Render one persisted round with its cluster facts and outcomes."""
    cases = _cluster_cases(facts, round_.probe_cluster_id)
    return StepRound(
        round_id=round_.id,
        cluster_id=round_.probe_cluster_id,
        title=cluster.probe_cluster_description if cluster else "",
        category=(cluster.probe_cluster_type if cluster else "error"),
        case_count=len(cases),
        confidence=cluster.confidence if cluster else None,
        severity=cluster.severity if cluster else None,
        cases=cases,
        status=cast(RoundStatus, round_.status),
        candidate=(
            StepCandidate(
                ref=round_.candidate_ref or "",
                commit=round_.candidate_commit or "",
                message=round_.candidate_message or "",
            )
            if round_.candidate_ref is not None
            else None
        ),
        patch=_round_patch(round_.patch),
        push=StepRoundPush(
            status=cast(RoundPushStatus, round_.push_status),
            attempts=round_.push_attempts,
            error=round_.push_error,
        ),
        eval=StepRoundEval(
            status=cast(RoundEvalStatus, round_.eval_status),
            current=round_.eval_current,
            candidate=round_.eval_candidate,
            next_poll_at=round_.eval_next_poll_at,
        ),
        accepted=round_.accepted,
        final_commit=(
            StepFinalCommit(
                hash=round_.commit_hash or "",
                message=round_.commit_message or "",
            )
            if round_.commit_hash is not None
            else None
        ),
    )
