"""Shared potential matcher and the read-only three-stage preview service.

The matcher owns every object-entry, trigger-anchor, ordering, and policy rule.
Wizard preview, run prepare, and overview are expected to call this one module
instead of re-deriving counts; preview itself never writes a probe, an
attribution link, or a run candidate.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cmp_to_key
from typing import Literal

from pydantic import Field, field_validator

from app.constants import POST_PROCESS_EVENT_INDEX
from app.db.crud.attributions import attribution_cache_key
from app.db.crud.evolution_targets import EvolutionTargetRecord
from app.db.crud.potential import (
    AgentNodeRecord,
    AnchorEventRecord,
    ObjectEventRecord,
    ObjectType,
    PotentialRepository,
    WindowCaseRecord,
    window_day_boundaries,
)
from app.errors import AppError, ErrorCode
from app.service.evolution.target_content import (
    TargetVersionResolver,
    resolve_legacy_target_version,
)
from app.service.evolution.targets import EvolutionTargetService
from app.service.identity.schemas import IdentityModel
from app.utils.time import now_shanghai

OrderState = Literal["comparable", "unknown"]
HitReason = Literal[
    "self_report",
    "after_object",
    "both",
    "policy_excluded",
    "order_unknown",
]
AnchorSource = Literal["event", "node", "post_process", "unknown"]

POLICY_VERSION = "v1"
"""Attribution policy semantics version inside the cache key."""

ATTRIBUTION_ENGINE = "rule-v1"
"""The only V2 attribution engine; previews read keys it would generate."""

DEFAULT_WINDOW_DAYS = 90
"""Window used when the request carries neither boundary."""

MAX_WINDOW_DAYS = 366
"""Largest inclusive preview window; a longer span is a 422."""

MIN_SUPPORTED_DATE = date(1970, 1, 1)
"""Earliest local boundary accepted; earlier dates are out of contract."""

MAX_SUPPORTED_DATE = date(2999, 12, 31)
"""Latest local boundary; leaves room for the half-open end predicate."""

SESSIONS_PAGE_SIZE = 4
"""Wizard step 2 page size from design 05 §4.20."""

POTENTIAL_PAGE_SIZE = 5
"""Wizard step 3 page size from design 05 §4.20."""

MAX_TARGET_VERSION_LENGTH = 96
"""Longest target version/revision accepted; a digest revision is 71 chars."""

REVISION_PREFIXES: tuple[str, ...] = ("tag:", "digest:", "provider:")
"""Normalized revision prefixes persisted in `agent_events.object_revision`."""

REASONS: tuple[HitReason, ...] = (
    "self_report",
    "after_object",
    "both",
    "policy_excluded",
    "order_unknown",
)


def resolve_target_revision(value: str) -> tuple[str, str]:
    """Resolve one stored version input into its legacy revision identity.

    This is the pre-content-resolver contract used by historical rows, the
    overview, and tests. New wizard/launch resolutions must call
    :class:`~app.service.evolution.target_content.TargetContentResolver` so a
    bare skill/agent tag becomes ``digest:<sha256(body)>``.

    Args:
        value: Trimmed ``targetVersion``, ``defaultRef``, or digest revision.

    Returns:
        The raw version and the normalized revision.
    """
    resolved = resolve_legacy_target_version(value)
    return resolved.target_version, resolved.target_revision


class PotentialPolicy(IdentityModel):
    """Raw policy switches accepted by the preview and launch contracts."""

    preset: Literal["default", "custom"] = "default"
    include_self_report: bool | None = None
    include_after_object: bool | None = None
    same_object_only: bool | None = None


@dataclass(frozen=True, slots=True)
class ResolvedPolicy:
    """Validated policy with explicit switches for every preset."""

    preset: str
    include_self_report: bool
    include_after_object: bool
    same_object_only: bool

    def snapshot(self) -> dict[str, object]:
        """Return the camelCase policy snapshot a run should persist."""
        return {
            "preset": self.preset,
            "includeSelfReport": self.include_self_report,
            "includeAfterObject": self.include_after_object,
            "sameObjectOnly": self.same_object_only,
        }


def _policy_invalid(reason: str) -> AppError:
    """Return the stable 422 for an unusable policy combination."""
    return AppError(
        status_code=422,
        code=ErrorCode.POLICY_INVALID,
        message="potential policy is invalid",
        details={"reason": reason},
    )


def resolve_policy(policy: PotentialPolicy | None) -> ResolvedPolicy:
    """Validate a policy preset and expand it into explicit switches.

    Args:
        policy: Request policy, or ``None`` to select the documented default.

    Returns:
        The validated policy with every switch materialized.

    Raises:
        AppError: With ``POLICY_INVALID`` when default carries switches, custom
            omits a switch, or custom enables neither matching rule.
    """
    if policy is None or policy.preset == "default":
        switches = (
            policy.include_self_report if policy is not None else None,
            policy.include_after_object if policy is not None else None,
            policy.same_object_only if policy is not None else None,
        )
        if any(switch is not None for switch in switches):
            raise _policy_invalid("default_preset_carries_switches")
        return ResolvedPolicy(
            preset="default",
            include_self_report=True,
            include_after_object=True,
            same_object_only=False,
        )
    if (
        policy.include_self_report is None
        or policy.include_after_object is None
        or policy.same_object_only is None
    ):
        raise _policy_invalid("custom_preset_requires_all_switches")
    include_self = bool(policy.include_self_report)
    include_after = bool(policy.include_after_object)
    if not (include_self or include_after):
        raise _policy_invalid("custom_preset_requires_enabled_rule")
    return ResolvedPolicy(
        preset="custom",
        include_self_report=include_self,
        include_after_object=include_after,
        same_object_only=bool(policy.same_object_only),
    )


class PreviewCondition(IdentityModel):
    """Target and window condition shared by the three preview stages."""

    target_type: ObjectType
    target_name: str = Field(min_length=1, max_length=128)
    target_version: str | None = Field(default=None, max_length=MAX_TARGET_VERSION_LENGTH)
    window_from: date | None = Field(default=None, alias="from")
    window_to: date | None = Field(default=None, alias="to")

    @field_validator("target_name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        """Trim a pasted object name before length validation."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("target_version", mode="before")
    @classmethod
    def _strip_version(cls, value: object) -> object:
        """Treat a blank explicit version as omitted so defaultRef applies."""
        if isinstance(value, str):
            return value.strip() or None
        return value


class SessionsPreviewRequest(PreviewCondition):
    """Session stage condition with 4 rows per page."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=SESSIONS_PAGE_SIZE, ge=1, le=50)


class PotentialPreviewRequest(SessionsPreviewRequest):
    """Potential stage condition: pagination plus the optional policy."""

    page_size: int = Field(default=POTENTIAL_PAGE_SIZE, ge=1, le=50)
    policy: PotentialPolicy | None = None


class AttributionPreviewRequest(PreviewCondition):
    """Attribution stage condition; preview never executes an engine."""

    policy: PotentialPolicy | None = None
    cache_enabled: bool = True


class SessionPreviewItem(IdentityModel):
    """One associated Session row in wizard step 2."""

    session_id: str
    short: str
    title: str
    object_trigger_at: datetime = Field(
        description=(
            "Object entry instant; falls back to the Session startedAt when the "
            "entry event has no triggeredAt. Comparison still uses coordinates "
            "when either side lacks a timestamp."
        ),
    )
    bad_case_count: int = Field(ge=0)


class SessionPreviewSummary(IdentityModel):
    """Non-overlapping Session partition for wizard step 2."""

    reported: int = Field(ge=0)
    associated: int = Field(ge=0)
    skipped: int = Field(ge=0)
    version_unresolved: int = Field(ge=0)
    pending: int = Field(ge=0)


class SessionPreviewResult(IdentityModel):
    """Paged associated Session projection."""

    summary: SessionPreviewSummary
    items: list[SessionPreviewItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    target_revision: str | None = None


class PotentialPreviewItem(IdentityModel):
    """One included bad case row in wizard step 3."""

    bad_case_id: str
    object_name: str
    bad_case_type: str
    trigger_at: datetime
    session_id: str
    hit_reason: HitReason
    order_state: OrderState
    anchor_source: AnchorSource


class PotentialReasonCounts(IdentityModel):
    """Every closed hit reason, zero-filled for a stable contract."""

    self_report: int = Field(default=0, ge=0)
    after_object: int = Field(default=0, ge=0)
    both: int = Field(default=0, ge=0)
    policy_excluded: int = Field(default=0, ge=0)
    order_unknown: int = Field(default=0, ge=0)


class PotentialPreviewSummary(IdentityModel):
    """Evaluated cases, included potential, and reason distribution."""

    bad_cases: int = Field(ge=0)
    potential: int = Field(ge=0)
    by_reason: PotentialReasonCounts


class PotentialPreviewResult(IdentityModel):
    """Paged potential rows; excluded rows stay in the summary only."""

    summary: PotentialPreviewSummary
    items: list[PotentialPreviewItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    target_revision: str | None = None


class AttributionPreviewSummary(IdentityModel):
    """Cache reuse preview and the historical non-target reference count."""

    potential: int = Field(ge=0)
    reused: int = Field(ge=0)
    fresh: int = Field(ge=0)
    non_target_known: int = Field(ge=0)


class AttributionPreviewResult(IdentityModel):
    """Read-only attribution preview; it has no paged rows."""

    summary: AttributionPreviewSummary
    target_revision: str | None = None


@dataclass(frozen=True, slots=True)
class MatchCondition:
    """Normalized condition shared by preview and future run prepare."""

    workspace_id: str
    target_type: ObjectType
    target_name: str
    target_version: str
    target_revision: str
    window_start: datetime
    window_end: datetime

    @property
    def revision_candidates(self) -> frozenset[str]:
        """Return every persisted identity form accepted for this target."""
        candidates = {self.target_version, self.target_revision}
        for value in (self.target_version, self.target_revision):
            if value.startswith("tag:"):
                candidates.add(value[4:])
            elif value.startswith("digest:"):
                # Events persist the body hash bare in ``definition_hash`` and
                # with the digest prefix in ``object_revision``/``document_revision``.
                candidates.add(value[7:])
        return frozenset(candidates)


@dataclass(frozen=True, slots=True)
class TriggerPoint:
    """One comparable trigger instant plus its tree/event coordinates."""

    agent_id: str | None
    event_index: int | None
    triggered_at: datetime | None
    tree_index: int | None


@dataclass(frozen=True, slots=True)
class OrderComparison:
    """Whether a case trigger is strictly after the object entry point."""

    state: OrderState
    after: bool


@dataclass(frozen=True, slots=True)
class CaseVerdict:
    """One case's closed hit reason and whether the policy includes it."""

    hit_reason: HitReason
    included: bool


@dataclass(frozen=True, slots=True)
class AssociatedSession:
    """One Session whose trace contains the requested object version."""

    session_id: str
    short: str
    title: str
    started_at: datetime
    object_trigger_at: datetime
    object_entry: TriggerPoint
    bad_case_count: int


@dataclass(frozen=True, slots=True)
class SessionAssociation:
    """Complete session-association output plus the window case snapshot."""

    reported: int
    associated: int
    skipped: int
    version_unresolved: int
    pending: int
    sessions: tuple[AssociatedSession, ...]
    cases: tuple[WindowCaseRecord, ...]


@dataclass(frozen=True, slots=True)
class PotentialCase:
    """One evaluated window case with both trigger points and its verdict."""

    bad_case_id: str
    session_id: str
    object_name: str
    bad_case_type: str
    trigger_at: datetime
    hit_reason: HitReason
    order_state: OrderState
    included: bool
    object_trigger: TriggerPoint
    case_trigger: TriggerPoint | None
    anchor_source: AnchorSource = "unknown"


@dataclass(frozen=True, slots=True)
class PotentialMatch:
    """All evaluated cases, the included subset, and the reason counts."""

    cases: tuple[PotentialCase, ...]
    included: tuple[PotentialCase, ...]
    by_reason: Mapping[HitReason, int]

    @property
    def potential(self) -> int:
        """Return the number of cases selected by the policy."""
        return len(self.included)


@dataclass(frozen=True, slots=True)
class AttributionPreviewCounts:
    """The four numbers wizard step 4 displays."""

    potential: int
    reused: int
    fresh: int
    non_target_known: int


def compare_triggers(
    case: TriggerPoint | None,
    target: TriggerPoint,
    *,
    post_process: bool = False,
) -> OrderComparison:
    """Compare a case anchor against the object entry point.

    A post-process anchor is defined as "after the object" regardless of its
    audit ``created_at`` (which can precede the entry in imported data). For
    every other anchor, wall-clock timestamps win when both sides carry one;
    otherwise the ``(tree_index, event_index)`` lexicographic order is used. A
    missing anchor or incomplete coordinates stay ``unknown`` and never satisfy
    "after".

    Args:
        case: Resolved bad-case anchor, or ``None`` when it cannot be resolved.
        target: Object entry point from a version-matched `agent_events` row.
        post_process: Whether the case anchor is the explicit post-process kind.

    Returns:
        The comparable/unknown state and the strict ``after`` verdict.
    """
    if case is None:
        return OrderComparison(state="unknown", after=False)
    if post_process:
        return OrderComparison(state="comparable", after=True)
    if case.triggered_at is not None and target.triggered_at is not None:
        return OrderComparison(
            state="comparable",
            after=case.triggered_at > target.triggered_at,
        )
    if (
        case.tree_index is not None
        and case.event_index is not None
        and target.tree_index is not None
        and target.event_index is not None
    ):
        return OrderComparison(
            state="comparable",
            after=(case.tree_index, case.event_index) > (target.tree_index, target.event_index),
        )
    return OrderComparison(state="unknown", after=False)


def evaluate_hit(
    *,
    self_match: bool,
    after_match: bool,
    order_state: OrderState,
    same_object: bool,
    policy: ResolvedPolicy,
) -> CaseVerdict:
    """Apply one resolved policy to one case's raw rule matches.

    Args:
        self_match: The case reports the target name with ``bad_case_type=self``.
        after_match: The case trigger is strictly after the object entry point.
        order_state: Whether the two trigger points were comparable.
        same_object: The case's reported object name equals the target name.
        policy: Validated policy switches.

    Returns:
        The closed reason (``both`` > ``self_report`` > ``after_object`` priority)
        and whether the case belongs to the potential set.
    """
    if policy.same_object_only and not same_object:
        return CaseVerdict(hit_reason="policy_excluded", included=False)
    self_hit = self_match and policy.include_self_report
    after_hit = after_match and order_state == "comparable" and policy.include_after_object
    if self_hit and after_hit:
        return CaseVerdict(hit_reason="both", included=True)
    if self_hit:
        return CaseVerdict(hit_reason="self_report", included=True)
    if after_hit:
        return CaseVerdict(hit_reason="after_object", included=True)
    if policy.include_after_object and order_state == "unknown":
        return CaseVerdict(hit_reason="order_unknown", included=False)
    return CaseVerdict(hit_reason="policy_excluded", included=False)


def resolve_window(
    window_from: date | None,
    window_to: date | None,
    *,
    today: date | None = None,
) -> tuple[date, date]:
    """Resolve the inclusive local-date window used by every preview stage.

    Args:
        window_from: Optional inclusive start date.
        window_to: Optional inclusive end date.
        today: Injectable current local date; defaults to Asia/Shanghai today.

    Returns:
        The inclusive start and end dates (never more than 366 days apart).

    Raises:
        AppError: With ``WINDOW_INVALID`` for an inverted or oversized window.
    """
    anchor = today or now_shanghai().date()
    start = (
        window_from if window_from is not None else anchor - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    )
    end = window_to if window_to is not None else anchor
    if window_from is None and window_to is not None:
        start = end - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if start > end:
        raise _window_invalid("from is after to", start, end)
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        raise _window_invalid("window is longer than 366 days", start, end)
    if start < MIN_SUPPORTED_DATE or end > MAX_SUPPORTED_DATE:
        raise _window_invalid("window is outside the supported date range", start, end)
    return start, end


def _window_invalid(reason: str, start: date, end: date) -> AppError:
    """Return the stable 422 for an unusable preview window."""
    return AppError(
        status_code=422,
        code=ErrorCode.WINDOW_INVALID,
        message="invalid preview time window",
        details={
            "reason": reason,
            "from": start.isoformat(),
            "to": end.isoformat(),
        },
    )


class PotentialMatcher:
    """Single implementation of session association, potential, and cache preview."""

    def __init__(self, repository: PotentialRepository) -> None:
        """Bind the matcher to its read-only repository."""
        self._repository = repository

    async def associated_sessions(self, condition: MatchCondition) -> SessionAssociation:
        """Return Sessions whose trace contains the requested object identity.

        Args:
            condition: Normalized workspace, object, version, revision, and window.

        Returns:
            The non-overlapping Session partition plus the window case snapshot.
        """
        cases = await self._repository.list_window_cases(
            workspace_id=condition.workspace_id,
            window_start=condition.window_start,
            window_end=condition.window_end,
        )
        session_ids = tuple(sorted({case.session_id for case in cases}))
        if not session_ids:
            return SessionAssociation(
                reported=0,
                associated=0,
                skipped=0,
                version_unresolved=0,
                pending=0,
                sessions=(),
                cases=(),
            )
        metas = await self._repository.list_sessions(session_ids)
        traced = tuple(session_id for session_id in session_ids if session_id in metas)
        events = await self._repository.list_object_events(
            traced,
            object_type=condition.target_type,
            object_name=condition.target_name,
        )
        events_by_session: dict[str, list[ObjectEventRecord]] = {}
        for event in events:
            events_by_session.setdefault(event.session_id, []).append(event)
        case_counts = Counter(case.session_id for case in cases)

        candidates = condition.revision_candidates
        associated: list[AssociatedSession] = []
        version_unresolved: list[str] = []
        skipped: list[str] = []
        for session_id in traced:
            session_events = events_by_session.get(session_id, [])
            matching = [event for event in session_events if _event_matches(event, candidates)]
            if matching:
                entry = min(matching, key=cmp_to_key(_compare_entry_order))
                associated.append(
                    AssociatedSession(
                        session_id=session_id,
                        short=metas[session_id].short_title,
                        title=metas[session_id].title,
                        started_at=metas[session_id].started_at,
                        object_trigger_at=(
                            entry.triggered_at
                            if entry.triggered_at is not None
                            else metas[session_id].started_at
                        ),
                        object_entry=TriggerPoint(
                            agent_id=entry.agent_id,
                            event_index=entry.event_index,
                            triggered_at=entry.triggered_at,
                            tree_index=entry.tree_index,
                        ),
                        bad_case_count=case_counts.get(session_id, 0),
                    ),
                )
            elif any(_event_revision_unresolved(event) for event in session_events):
                version_unresolved.append(session_id)
            else:
                skipped.append(session_id)

        pending = tuple(session_id for session_id in session_ids if session_id not in metas)
        associated.sort(key=_associated_order_key)
        return SessionAssociation(
            reported=len(session_ids),
            associated=len(associated),
            skipped=len(skipped),
            version_unresolved=len(version_unresolved),
            pending=len(pending),
            sessions=tuple(associated),
            cases=cases,
        )

    async def potential_cases(
        self,
        condition: MatchCondition,
        association: SessionAssociation,
        policy: ResolvedPolicy,
    ) -> PotentialMatch:
        """Evaluate the policy against every window case of associated Sessions.

        Args:
            condition: Normalized workspace, object, version, and window.
            association: Output of :meth:`associated_sessions` for the same input.
            policy: Validated policy switches.

        Returns:
            Every evaluated case, the included subset, and closed reason counts.
        """
        associated_ids = {session.session_id for session in association.sessions}
        cases = tuple(case for case in association.cases if case.session_id in associated_ids)
        if not cases:
            return PotentialMatch(cases=(), included=(), by_reason=_empty_reasons())

        session_ids = tuple(sorted(associated_ids))
        agents = await self._repository.list_agents(session_ids)
        agents_by_id = {agent.id: agent for agent in agents}
        mains: dict[str, AgentNodeRecord] = {}
        for agent in agents:
            if agent.kind == "main":
                mains.setdefault(agent.root_session_id, agent)

        involved: set[str] = set()
        skill_names: set[str] = set()
        reporters: dict[str, AgentNodeRecord | None] = {}
        for case in cases:
            reporter = _reporter_for(case, agents_by_id, mains)
            reporters[case.bad_case_id] = reporter
            if reporter is None:
                continue
            involved.add(reporter.id)
            if case.object_type == "skill":
                skill_names.add(case.object_name)
            if reporter.parent_agent_id is not None:
                involved.add(reporter.parent_agent_id)

        anchor_events = await self._repository.list_anchor_events(
            tuple(sorted(involved)),
            tuple(sorted(skill_names)),
        )
        events_by_agent: dict[str, list[AnchorEventRecord]] = {}
        for event in anchor_events:
            events_by_agent.setdefault(event.agent_id, []).append(event)
        entries = {session.session_id: session for session in association.sessions}

        evaluated: list[PotentialCase] = []
        for case in cases:
            session = entries.get(case.session_id)
            if session is None:
                continue
            case_trigger, anchor_source = _resolve_case_trigger(
                case,
                reporters[case.bad_case_id],
                agents_by_id,
                events_by_agent,
                session.started_at,
            )
            comparison = compare_triggers(
                case_trigger,
                session.object_entry,
                post_process=anchor_source == "post_process",
            )
            same_object = case.object_name == condition.target_name
            verdict = evaluate_hit(
                self_match=same_object and case.bad_case_type == "self",
                after_match=comparison.after,
                order_state=comparison.state,
                same_object=same_object,
                policy=policy,
            )
            evaluated.append(
                PotentialCase(
                    bad_case_id=case.bad_case_id,
                    session_id=case.session_id,
                    object_name=case.object_name,
                    bad_case_type=case.bad_case_type,
                    trigger_at=(
                        case_trigger.triggered_at
                        if case_trigger is not None and case_trigger.triggered_at is not None
                        else case.created_at
                    ),
                    hit_reason=verdict.hit_reason,
                    order_state=comparison.state,
                    included=verdict.included,
                    object_trigger=session.object_entry,
                    case_trigger=case_trigger,
                    anchor_source=anchor_source,
                ),
            )

        by_reason = _empty_reasons()
        for item in evaluated:
            by_reason[item.hit_reason] += 1
        included = tuple(item for item in evaluated if item.included)
        return PotentialMatch(
            cases=tuple(evaluated),
            included=included,
            by_reason=by_reason,
        )

    async def attribution_preview(
        self,
        condition: MatchCondition,
        match: PotentialMatch,
        *,
        cache_enabled: bool,
    ) -> AttributionPreviewCounts:
        """Count existing cache keys and the historical non-target reference.

        Args:
            condition: Normalized workspace, object, version, and window.
            match: Potential output whose included subset owns the cache keys.
            cache_enabled: When false the run would ignore cache, so ``reused`` is 0.

        Returns:
            The four numbers wizard step 4 displays; nothing is written.
        """
        reused = 0
        if cache_enabled and match.included:
            keys = tuple(
                attribution_cache_key(
                    condition.workspace_id,
                    item.bad_case_id,
                    condition.target_type,
                    condition.target_name,
                    condition.target_revision,
                    POLICY_VERSION,
                    ATTRIBUTION_ENGINE,
                )
                for item in match.included
            )
            reused = len(await self._repository.existing_cache_keys(keys))
        non_target_known = await self._repository.count_non_target_cases(
            workspace_id=condition.workspace_id,
            probe_type=condition.target_type,
            probe_object=condition.target_name,
            object_versions=tuple(sorted(condition.revision_candidates)),
        )
        return AttributionPreviewCounts(
            potential=match.potential,
            reused=reused,
            fresh=match.potential - reused,
            non_target_known=non_target_known,
        )


class PotentialPreviewService:
    """Resolve the three preview stages through the shared matcher."""

    def __init__(
        self,
        targets: EvolutionTargetService,
        matcher: PotentialMatcher,
        resolver: TargetVersionResolver,
    ) -> None:
        """Bind target configuration validation, the matcher, and content resolution."""
        self._targets = targets
        self._matcher = matcher
        self._resolver = resolver

    async def sessions(
        self,
        body: SessionsPreviewRequest,
        *,
        workspace_id: str,
    ) -> SessionPreviewResult:
        """Return paged associated Sessions plus the non-overlapping partition."""
        condition = await self._condition(body, workspace_id=workspace_id)
        association = await self._matcher.associated_sessions(condition)
        if not association.sessions:
            raise _no_associated_sessions(association)
        items = [
            SessionPreviewItem(
                session_id=session.session_id,
                short=session.short,
                title=session.title,
                object_trigger_at=session.object_trigger_at,
                bad_case_count=session.bad_case_count,
            )
            for session in association.sessions
        ]
        start = (body.page - 1) * body.page_size
        return SessionPreviewResult(
            summary=SessionPreviewSummary(
                reported=association.reported,
                associated=association.associated,
                skipped=association.skipped,
                version_unresolved=association.version_unresolved,
                pending=association.pending,
            ),
            items=items[start : start + body.page_size],
            total=len(items),
            page=body.page,
            page_size=body.page_size,
            target_revision=condition.target_revision,
        )

    async def potential(
        self,
        body: PotentialPreviewRequest,
        *,
        workspace_id: str,
    ) -> PotentialPreviewResult:
        """Return paged included cases plus the closed reason distribution."""
        condition = await self._condition(body, workspace_id=workspace_id)
        policy = resolve_policy(body.policy)
        association = await self._matcher.associated_sessions(condition)
        if not association.sessions:
            raise _no_associated_sessions(association)
        match = await self._matcher.potential_cases(condition, association, policy)
        if not match.included:
            raise _no_potential_matched()
        ordered = sorted(
            match.included,
            key=lambda item: (-item.trigger_at.timestamp(), item.bad_case_id),
        )
        start = (body.page - 1) * body.page_size
        page_items = ordered[start : start + body.page_size]
        return PotentialPreviewResult(
            summary=PotentialPreviewSummary(
                bad_cases=len(match.cases),
                potential=match.potential,
                by_reason=PotentialReasonCounts(
                    self_report=match.by_reason.get("self_report", 0),
                    after_object=match.by_reason.get("after_object", 0),
                    both=match.by_reason.get("both", 0),
                    policy_excluded=match.by_reason.get("policy_excluded", 0),
                    order_unknown=match.by_reason.get("order_unknown", 0),
                ),
            ),
            items=[_potential_item(item) for item in page_items],
            total=len(ordered),
            page=body.page,
            page_size=body.page_size,
            target_revision=condition.target_revision,
        )

    async def attribution(
        self,
        body: AttributionPreviewRequest,
        *,
        workspace_id: str,
    ) -> AttributionPreviewResult:
        """Return cache reuse counts without executing or writing attribution."""
        condition = await self._condition(body, workspace_id=workspace_id)
        policy = resolve_policy(body.policy)
        association = await self._matcher.associated_sessions(condition)
        if not association.sessions:
            raise _no_associated_sessions(association)
        match = await self._matcher.potential_cases(condition, association, policy)
        if not match.included:
            raise _no_potential_matched()
        counts = await self._matcher.attribution_preview(
            condition,
            match,
            cache_enabled=body.cache_enabled,
        )
        return AttributionPreviewResult(
            summary=AttributionPreviewSummary(
                potential=counts.potential,
                reused=counts.reused,
                fresh=counts.fresh,
                non_target_known=counts.non_target_known,
            ),
            target_revision=condition.target_revision,
        )

    async def _condition(
        self,
        body: PreviewCondition,
        *,
        workspace_id: str,
    ) -> MatchCondition:
        """Validate the target/window and resolve the version and day bounds."""
        config = await self._targets.enabled_config(
            body.target_type,
            body.target_name,
            workspace_ids=(workspace_id,),
        )
        version = (body.target_version or config.default_ref or "").strip()
        if not version:
            raise AppError(
                status_code=422,
                code=ErrorCode.VALIDATION_INVALID,
                message="target version is required",
            )
        if len(version) > MAX_TARGET_VERSION_LENGTH:
            raise AppError(
                status_code=422,
                code=ErrorCode.VALIDATION_INVALID,
                message="target version is too long",
                details={
                    "field": "targetVersion",
                    "maxLength": MAX_TARGET_VERSION_LENGTH,
                },
            )
        target_version, target_revision = await self._resolve_version(body, config, version)
        start, end = resolve_window(body.window_from, body.window_to)
        window_start, window_end = window_day_boundaries(start, end)
        return MatchCondition(
            workspace_id=workspace_id,
            target_type=body.target_type,
            target_name=body.target_name,
            target_version=target_version,
            target_revision=target_revision,
            window_start=window_start,
            window_end=window_end,
        )

    async def _resolve_version(
        self,
        body: PreviewCondition,
        config: EvolutionTargetRecord,
        version: str,
    ) -> tuple[str, str]:
        """Resolve a selected version to its persisted body-hash revision."""
        resolved = await self._resolver.resolve(
            object_type=body.target_type,
            repo_url=config.repo_url,
            sub_dir=config.sub_dir,
            version=version,
        )
        return resolved.target_version, resolved.target_revision


def _potential_item(item: PotentialCase) -> PotentialPreviewItem:
    """Map one included matcher result to the wizard row DTO."""
    return PotentialPreviewItem(
        bad_case_id=item.bad_case_id,
        object_name=item.object_name,
        bad_case_type=item.bad_case_type,
        trigger_at=item.trigger_at,
        session_id=item.session_id,
        hit_reason=item.hit_reason,
        order_state=item.order_state,
        anchor_source=item.anchor_source,
    )


def _reporter_for(
    case: WindowCaseRecord,
    agents_by_id: Mapping[str, AgentNodeRecord],
    mains: Mapping[str, AgentNodeRecord],
) -> AgentNodeRecord | None:
    """Resolve the reporting Agent, defaulting an absent id to the main Agent.

    A blank id counts as absent. A non-empty id that resolves to another Session
    is invalid evidence, so it stays unresolved instead of being reassigned.
    """
    if case.bad_case_agent_id:
        reporter = agents_by_id.get(case.bad_case_agent_id)
        if reporter is None or reporter.root_session_id != case.session_id:
            return None
        return reporter
    return mains.get(case.session_id)


def _resolve_case_trigger(
    case: WindowCaseRecord,
    reporter: AgentNodeRecord | None,
    agents_by_id: Mapping[str, AgentNodeRecord],
    events_by_agent: Mapping[str, Sequence[AnchorEventRecord]],
    session_started_at: datetime,
) -> tuple[TriggerPoint | None, AnchorSource]:
    """Resolve the 06 §7.4 anchor and its audited ``anchorSource``.

    A resolved reporter with a missing skill/agent trigger becomes an explicit
    post-process anchor instead of silently degrading to the reporter's birth
    point. Only an unresolvable reporter remains ``unknown``/``-1``.
    """
    if reporter is None:
        return None, "unknown"
    if case.object_type == "skill":
        skill_events = [
            event
            for event in events_by_agent.get(reporter.id, ())
            if event.kind == "skill" and event.name == case.object_name
        ]
        if skill_events:
            last = max(skill_events, key=lambda event: event.event_index)
            return (
                TriggerPoint(
                    agent_id=reporter.id,
                    event_index=last.event_index,
                    triggered_at=last.triggered_at,
                    tree_index=reporter.tree_index,
                ),
                "event",
            )
        return _post_process_anchor(case, reporter), "post_process"
    if case.bad_case_type == "discovery" and case.object_type == "agent":
        parent = (
            agents_by_id.get(reporter.parent_agent_id)
            if reporter.parent_agent_id is not None
            else None
        )
        call = _parent_call_event(parent, reporter, events_by_agent)
        if parent is not None and call is not None:
            return (
                TriggerPoint(
                    agent_id=parent.id,
                    event_index=call.event_index,
                    triggered_at=call.triggered_at,
                    tree_index=parent.tree_index,
                ),
                "event",
            )
        return _post_process_anchor(case, reporter), "post_process"
    return (
        _node_anchor(
            reporter,
            agents_by_id,
            events_by_agent,
            session_started_at,
        ),
        "node",
    )


def _post_process_anchor(
    case: WindowCaseRecord,
    reporter: AgentNodeRecord,
) -> TriggerPoint:
    """Build the explicit after-everything anchor for an unmatched report."""
    return TriggerPoint(
        agent_id=reporter.id,
        event_index=POST_PROCESS_EVENT_INDEX,
        triggered_at=case.created_at,
        # The coordinate fallback shares the same INT_MAX sentinel.
        tree_index=POST_PROCESS_EVENT_INDEX,
    )


def _node_anchor(
    reporter: AgentNodeRecord,
    agents_by_id: Mapping[str, AgentNodeRecord],
    events_by_agent: Mapping[str, Sequence[AnchorEventRecord]],
    session_started_at: datetime,
) -> TriggerPoint:
    """Return the reporter node anchor used by ``self + agent`` reports."""
    triggered_at: datetime | None
    if reporter.kind == "main":
        triggered_at = session_started_at
    elif reporter.parent_agent_id is None:
        triggered_at = None
    else:
        parent = agents_by_id.get(reporter.parent_agent_id)
        call = _parent_call_event(parent, reporter, events_by_agent)
        triggered_at = call.triggered_at if call is not None else None
    return TriggerPoint(
        agent_id=reporter.id,
        event_index=-1,
        triggered_at=triggered_at,
        tree_index=reporter.tree_index,
    )


def _parent_call_event(
    parent: AgentNodeRecord | None,
    reporter: AgentNodeRecord,
    events_by_agent: Mapping[str, Sequence[AnchorEventRecord]],
) -> AnchorEventRecord | None:
    """Find the parent's Agent event whose tool_use_id created the reporter."""
    if parent is None or reporter.tool_use_id is None:
        return None
    matches = [
        event
        for event in events_by_agent.get(parent.id, ())
        if event.kind == "agent" and event.tool_use_id == reporter.tool_use_id
    ]
    return min(matches, key=lambda event: event.event_index) if matches else None


def _compare_entry_order(left: ObjectEventRecord, right: ObjectEventRecord) -> int:
    """Order entry events with the same time-vs-coordinate rule as comparisons."""
    if (
        left.triggered_at is not None
        and right.triggered_at is not None
        and left.triggered_at != right.triggered_at
    ):
        return -1 if left.triggered_at < right.triggered_at else 1
    left_key = (left.tree_index, left.event_index)
    right_key = (right.tree_index, right.event_index)
    return (left_key > right_key) - (left_key < right_key)


def _event_matches(event: ObjectEventRecord, candidates: frozenset[str]) -> bool:
    """Return whether any persisted identity form matches the target."""
    return any(
        value is not None and value in candidates
        for value in (
            event.object_version,
            event.object_revision,
            event.definition_hash,
            event.document_revision,
        )
    )


def _event_revision_unresolved(event: ObjectEventRecord) -> bool:
    """Return whether an event carries no usable version or revision identity."""
    if event.object_version is not None:
        return False
    return not any(
        value is not None and value != "unknown"
        for value in (
            event.object_revision,
            event.definition_hash,
            event.document_revision,
        )
    )


def _associated_order_key(
    session: AssociatedSession,
) -> tuple[int, float, str]:
    """Sort associated Sessions newest object entry first."""
    return (0, -session.object_trigger_at.timestamp(), session.session_id)


def _empty_reasons() -> dict[HitReason, int]:
    """Return the zero-filled closed reason distribution."""
    return {reason: 0 for reason in REASONS}


def _no_associated_sessions(association: SessionAssociation) -> AppError:
    """Return the stable 409 plus the Session partition that explains the empty page."""
    return AppError(
        status_code=409,
        code=ErrorCode.NO_ASSOCIATED_SESSIONS,
        message="no session is associated with the target in this window",
        details={
            "summary": {
                "reported": association.reported,
                "associated": association.associated,
                "skipped": association.skipped,
                "versionUnresolved": association.version_unresolved,
                "pending": association.pending,
            },
        },
    )


def _no_potential_matched() -> AppError:
    """Return the stable 409 for associated Sessions with no potential case."""
    return AppError(
        status_code=409,
        code=ErrorCode.NO_POTENTIAL_MATCHED,
        message="no bad case matches the potential policy",
    )
