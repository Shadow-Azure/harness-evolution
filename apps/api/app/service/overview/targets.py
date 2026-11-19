"""Evolution-target overview aggregation on top of the shared potential matcher.

The matcher owns association, potential policy, and trigger ordering. This
service only discovers which versions each configured target actually appeared
as, calls the matcher once per ``(target, version)`` pair, and projects the
resulting potential rows into the closed three-state vocabulary from 06 §7.5.
No endpoint here writes; every read is pinned to the path workspace.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, cast

from app.db.crud.evolution_targets import (
    EvolutionTargetRecord,
    EvolutionTargetRepository,
)
from app.db.crud.overview_targets import (
    AttributionLinkRecord,
    ObjectVersionRecord,
    TargetOverviewRepository,
    TargetRunVersionRecord,
    WindowCaseFact,
)
from app.db.crud.potential import window_day_boundaries
from app.errors import AppError, ErrorCode
from app.service.evolution.potential import (
    MatchCondition,
    PotentialCase,
    PotentialMatch,
    PotentialMatcher,
    ResolvedPolicy,
    SessionAssociation,
    resolve_policy,
)
from app.service.evolution.target_content import (
    ResolvedTargetVersion,
    TargetVersionResolver,
)
from app.service.overview.schemas import OverviewWindow
from app.service.overview.target_schemas import (
    TARGET_STATES,
    TargetCaseItem,
    TargetCaseListResponse,
    TargetDetailResponse,
    TargetDetailSource,
    TargetDetailStats,
    TargetDetailTarget,
    TargetDetailVersion,
    TargetOverviewItem,
    TargetOverviewListResponse,
    TargetOverviewSummary,
    TargetState,
    TargetTrendBucket,
    TargetTrendByTarget,
    TargetTrendMeta,
    TargetTrendResponse,
    TargetVersionOption,
)
from app.service.overview.window import Window, bucket_label, bucket_start, bucket_starts
from app.utils.time import as_shanghai

MAX_TARGETS = 50
"""Largest accepted target selection; a broader filter is a 422."""

MAX_VERSIONS = 50
"""Largest accepted explicit version selection; detail pages use at most 20."""

DEFAULT_TARGET_PAGE_SIZE = 5
"""Target-list page size from design 05 §4.18."""

DEFAULT_CASE_PAGE_SIZE = 8
"""Potential-case page size from design 05 §4.18."""

DEFAULT_VERSION_LIMIT = 5
"""Detail card's default newest-version window."""

ALLOWED_VERSION_LIMITS: frozenset[int] = frozenset({0, 5, 10, 20})
"""Explicit detail version-window choices; ``0`` means every observed version."""

BUCKET_POLICY = (
    "attributed and nonTarget rows bucket by attribution createdAt; "
    "unanalyzed rows bucket by badCase createdAt"
)
"""The exact bucket-time policy exposed through ``meta.bucketPolicy``."""

CATEGORIES: frozenset[str] = frozenset({"model", "prompt", "error"})
"""The closed attribution category set; anything else is not projected."""

_VERSION_PART = re.compile(r"(\d+)")

OVERVIEW_RESOLVE_TIMEOUT_SECONDS = 2.0
"""Keep one slow/unreachable target repository from blocking the overview page."""

OVERVIEW_RESOLVE_CONCURRENCY = 4
"""Bound concurrent content reads so a wide target page cannot spawn unbounded git."""

OVERVIEW_FAILURE_TTL_SECONDS = 30.0
"""Cache a failed version briefly so repeated reads fail fast instead of retrying."""

OVERVIEW_FAILURE_CACHE_SIZE = 512
"""Bound the negative-resolution cache."""

RUN_VERSION_LOOKBACK = 200
"""Newest runs read per target to recover ref/commit display evidence."""


@dataclass(frozen=True, slots=True)
class TargetOverviewQuery:
    """Validated shared window plus the target/case filters of one read."""

    window: Window
    targets: tuple[str, ...] = ()
    objects: tuple[str, ...] = ()
    states: frozenset[TargetState] = field(default_factory=lambda: frozenset(TARGET_STATES))
    versions: tuple[str, ...] = ()
    version_limit: int = DEFAULT_VERSION_LIMIT
    page: int = 1
    page_size: int = DEFAULT_TARGET_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class TargetCaseEntry:
    """One potential ``(badCaseId, targetVersion)`` row with its attribution state."""

    bad_case_id: str
    target: EvolutionTargetRecord
    version: str
    session_id: str
    source: str
    bad_case_type: str
    title: str
    created_at: datetime
    state: TargetState
    attribution_id: str | None
    category: Literal["model", "prompt", "error"] | None
    attributed_at: datetime | None
    display_version: str = ""
    """The ref shown to readers; falls back to the canonical key when unknown."""


@dataclass(frozen=True, slots=True)
class TargetVersionLabel:
    """One canonical version key plus the evidence used to display it.

    ``version`` is the digest identity that filtering and statistics use;
    ``ref`` and ``commit`` are display-only. ``aliases`` lets one version key
    accept every persisted identity form in filters and attribution links.
    """

    version: str
    ref: str | None
    commit: str | None
    aliases: frozenset[str]

    @property
    def display(self) -> str:
        """Return the primary text a reader sees for this version."""
        return self.ref or self.version


@dataclass(slots=True)
class _VersionAccumulator:
    """Mutable grouping state while observed trigger records are merged."""

    digest: str | None
    aliases: set[str]
    refs: list[str]


@dataclass(frozen=True, slots=True)
class TargetAnalysis:
    """One target's observed versions, associated Sessions, and potential rows."""

    target: EvolutionTargetRecord
    versions: tuple[str, ...]
    session_ids: frozenset[str]
    entries: tuple[TargetCaseEntry, ...]
    version_sessions: Mapping[str, frozenset[str]] = field(default_factory=dict)
    unresolved_versions: frozenset[str] = frozenset()
    version_labels: Mapping[str, TargetVersionLabel] = field(default_factory=dict)

    @property
    def sessions(self) -> int:
        """Return the distinct associated Session count across every version."""
        return len(self.session_ids)

    @property
    def potential(self) -> int:
        """Return the number of potential case-version rows."""
        return len(self.entries)

    @property
    def attributed(self) -> int:
        """Return potential rows whose newest attribution is ``attributed``."""
        return sum(1 for entry in self.entries if entry.state == "attributed")

    @property
    def non_target(self) -> int:
        """Return potential rows whose newest attribution is ``non_target``."""
        return sum(1 for entry in self.entries if entry.state == "nonTarget")

    @property
    def unanalyzed(self) -> int:
        """Return potential rows without a readable attribution link."""
        return sum(1 for entry in self.entries if entry.state == "unanalyzed")

    @property
    def evolvable(self) -> int:
        """Return attributed plus unanalyzed rows, the documented sort key."""
        return self.attributed + self.unanalyzed


def _split_values(values: Sequence[str] | None) -> tuple[str, ...]:
    """Flatten repeated and comma-separated filters into one ordered set."""
    if not values:
        return ()
    selected: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in raw.split(","):
            value = part.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            selected.append(value)
    return tuple(selected)


def _filter_invalid(reason: str, **details: object) -> AppError:
    """Return the stable 422 for an unusable target/state/version filter."""
    return AppError(
        status_code=422,
        code=ErrorCode.VALIDATION_INVALID,
        message=f"invalid target overview filter: {reason}",
        details={"reason": reason, **details},
    )


def parse_target_filter(values: Sequence[str] | None) -> tuple[str, ...]:
    """Parse the ``targets[]`` selection and reject a broad unbounded scope."""
    selected = _split_values(values)
    if len(selected) > MAX_TARGETS:
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_INVALID,
            message=f"at most {MAX_TARGETS} targets can be selected",
            details={"reason": "target_filter_too_large", "count": len(selected)},
        )
    return selected


def parse_state_filter(values: Sequence[str] | None) -> frozenset[TargetState]:
    """Parse ``states[]`` into the closed three-state set; empty means all."""
    if not values:
        return frozenset(TARGET_STATES)
    parsed = _split_values(values)
    if not parsed:
        return frozenset(TARGET_STATES)
    selected: list[TargetState] = []
    invalid: list[str] = []
    for value in parsed:
        if value not in TARGET_STATES:
            invalid.append(value)
            continue
        selected.append(value)
    if invalid:
        raise _filter_invalid(
            "unknown_state",
            states=invalid,
            allowed=list(TARGET_STATES),
        )
    return frozenset(selected)


def parse_version_limit(value: int) -> int:
    """Accept only the documented detail version-window choices."""
    if value not in ALLOWED_VERSION_LIMITS:
        raise _filter_invalid(
            "unsupported_version_limit",
            value=value,
            allowed=sorted(ALLOWED_VERSION_LIMITS),
        )
    return value


def parse_version_filter(values: Sequence[str] | None) -> tuple[str, ...]:
    """Parse ``versions[]`` for one target's detail card and bound the scope."""
    selected = _split_values(values)
    if len(selected) > MAX_VERSIONS:
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_INVALID,
            message=f"at most {MAX_VERSIONS} versions can be selected",
            details={"reason": "version_filter_too_large", "count": len(selected)},
        )
    return selected


def _display_version(value: str | None) -> str | None:
    """Normalize one persisted identity to the version a reader configured."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    display = trimmed[4:] if trimmed.startswith("tag:") else trimmed
    return display or None


def _known_version(value: str | None) -> str | None:
    """Normalize one persisted identity, dropping the documented unknown form."""
    display = _display_version(value)
    if display is None or display.lower() == "unknown":
        return None
    return display


def _record_identity(
    record: ObjectVersionRecord,
) -> tuple[str, frozenset[str], str | None, str | None] | None:
    """Collapse one trigger record's version/revision pair into one identity.

    A record that carries both a git ref and a body digest describes *one*
    version: the digest is the canonical identity and the ref is its display
    label. Treating them as two versions is what split the same production
    row into ``main`` and ``digest:…``.

    Returns:
        ``(canonical_key, aliases, ref, digest)`` or ``None`` when the record
        carries no usable identity.
    """
    version = _known_version(record.object_version)
    revision = _known_version(record.object_revision)
    if version is None and revision is None:
        return None
    aliases: set[str] = {value for value in (version, revision) if value is not None}
    digest: str | None = None
    for value in (version, revision):
        if value is not None and value.startswith("digest:"):
            digest = value
            break
    ref: str | None = None
    if version is not None and not version.startswith(("digest:", "provider:")):
        ref = version
    elif revision is not None and not revision.startswith(("digest:", "provider:")):
        ref = revision
    key = digest or version or revision
    if key is None:
        return None
    if digest is not None:
        # ``definition_hash`` and legacy probe rows persist the bare hash.
        aliases.add(digest[7:])
    return key, frozenset(aliases), ref, digest


def _version_accumulators(
    default_ref: str,
    observed: Sequence[ObjectVersionRecord],
) -> dict[str, _VersionAccumulator]:
    """Merge observed trigger records into canonical versions, newest-first later."""
    groups: dict[str, _VersionAccumulator] = {}
    for record in observed:
        identity = _record_identity(record)
        if identity is None:
            continue
        key, aliases, ref, digest = identity
        group = groups.get(key)
        if group is None:
            group = _VersionAccumulator(
                digest=digest,
                aliases=set(),
                refs=[],
            )
            groups[key] = group
        group.aliases.update(aliases)
        if digest is not None and group.digest is None:
            group.digest = digest
        if ref is not None and ref not in group.refs:
            group.refs.append(ref)
    default = _known_version(default_ref)
    if default is not None and not any(default in group.aliases for group in groups.values()):
        digest = default if default.startswith("digest:") else None
        group = _VersionAccumulator(
            digest=digest,
            aliases={default},
            refs=[],
        )
        if digest is not None:
            group.aliases.add(digest[7:])
        elif not default.startswith("provider:"):
            group.refs.append(default)
        groups[default] = group
    return groups


def _short_commit(value: str | None) -> str | None:
    """Return the seven-character commit prefix the prototype renders."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed[:7] if len(trimmed) >= 7 else None


def _version_sort_key(value: str) -> tuple[tuple[int, int, str], ...]:
    """Return a natural, case-insensitive descending-order key for a version."""
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part.lower())
        for part in _VERSION_PART.split(value)
        if part
    )


def _preferred_ref(
    refs: Sequence[str],
    run_ref: str | None,
    default_ref: str | None,
) -> str | None:
    """Pick one display ref for a digest that observations tie to several refs."""
    unique = list(dict.fromkeys(refs))
    if run_ref is not None:
        return run_ref
    if default_ref is not None and default_ref in unique:
        return default_ref
    if not unique:
        return None
    return max(unique, key=_version_sort_key)


def _build_version_labels(
    default_ref: str,
    observed: Sequence[ObjectVersionRecord],
    runs: Sequence[TargetRunVersionRecord],
) -> tuple[tuple[str, ...], dict[str, TargetVersionLabel]]:
    """Build canonical versions and their ref/commit display evidence.

    Runs are newest-first. A run is evidence for a digest when its
    ``target_revision`` matches; ref-only versions fall back to
    ``target_version``. No git lookup happens for digest-only history: it keeps
    the digest instead of guessing a moving ref.
    """
    groups = _version_accumulators(default_ref, observed)
    by_revision: dict[str, TargetRunVersionRecord] = {}
    by_ref: dict[str, TargetRunVersionRecord] = {}
    for run in runs:
        revision = _known_version(run.target_revision)
        if revision is not None:
            by_revision.setdefault(revision, run)
        ref = _known_version(run.target_version)
        if ref is not None:
            by_ref.setdefault(ref, run)
    default = _known_version(default_ref)
    labels: dict[str, TargetVersionLabel] = {}
    for key, group in groups.items():
        latest_run = by_revision.get(key) if group.digest is not None else by_ref.get(key)
        run_ref = _known_version(latest_run.target_version) if latest_run is not None else None
        if run_ref is not None and run_ref.startswith(("digest:", "provider:")):
            run_ref = None
        ref = _preferred_ref(group.refs, run_ref, default)
        if ref is None and group.digest is None:
            candidate = _known_version(key)
            ref = (
                candidate
                if candidate is not None and not candidate.startswith(("digest:", "provider:"))
                else None
            )
        labels[key] = TargetVersionLabel(
            version=key,
            ref=ref,
            commit=_short_commit(latest_run.base_commit) if latest_run is not None else None,
            aliases=frozenset(group.aliases),
        )
    ordered = tuple(
        sorted(
            labels,
            key=lambda key: (_version_sort_key(labels[key].display), key),
            reverse=True,
        ),
    )
    return ordered, labels


def _newest_link_by_case(
    links: Sequence[AttributionLinkRecord],
    aliases: frozenset[str],
) -> dict[str, AttributionLinkRecord]:
    """Keep the newest readable link per case for one version's every alias."""
    found: dict[str, AttributionLinkRecord] = {}
    for link in links:
        version = _display_version(link.object_version)
        if version is None or version not in aliases:
            continue
        found.setdefault(link.bad_case_id, link)
    return found


def _category(link: AttributionLinkRecord | None) -> Literal["model", "prompt", "error"] | None:
    """Project only the closed attribution category set."""
    if link is None or link.category not in CATEGORIES:
        return None
    return cast(Literal["model", "prompt", "error"], link.category)


def _state(link: AttributionLinkRecord | None) -> TargetState:
    """Map one newest link to the three-state vocabulary."""
    if link is None:
        return "unanalyzed"
    if link.conclusion == "attributed":
        return "attributed"
    return "nonTarget"


class TargetOverviewService:
    """Aggregate enabled targets through the matcher into the overview contracts."""

    def __init__(
        self,
        targets: EvolutionTargetRepository,
        repository: TargetOverviewRepository,
        matcher: PotentialMatcher,
        resolver: TargetVersionResolver,
        *,
        resolve_timeout_seconds: float = OVERVIEW_RESOLVE_TIMEOUT_SECONDS,
        failure_ttl_seconds: float = OVERVIEW_FAILURE_TTL_SECONDS,
    ) -> None:
        """Bind target configuration, read facts, the matcher, and content resolution."""
        self._targets = targets
        self._repository = repository
        self._matcher = matcher
        self._resolver = resolver
        self._policy: ResolvedPolicy = resolve_policy(None)
        self._resolve_timeout = resolve_timeout_seconds
        self._failure_ttl = failure_ttl_seconds
        self._resolve_slots = asyncio.Semaphore(OVERVIEW_RESOLVE_CONCURRENCY)
        self._failed_versions: OrderedDict[tuple[str, str, str, str], float] = OrderedDict()

    async def list_targets(
        self,
        workspace_id: str,
        query: TargetOverviewQuery,
    ) -> TargetOverviewListResponse:
        """Return summary totals and one evolvable-sorted target page."""
        analyses = await self._analyses(workspace_id, query.window, ())
        ordered = sorted(
            analyses,
            key=lambda analysis: (
                -analysis.evolvable,
                -analysis.potential,
                analysis.target.object_name.casefold(),
                analysis.target.object_type,
                analysis.target.id,
            ),
        )
        page_start = (query.page - 1) * query.page_size
        page = ordered[page_start : page_start + query.page_size]
        return TargetOverviewListResponse(
            summary=TargetOverviewSummary(
                targets=len(analyses),
                sessions=sum(analysis.sessions for analysis in analyses),
                potential=sum(analysis.potential for analysis in analyses),
                attributed=sum(analysis.attributed for analysis in analyses),
                non_target=sum(analysis.non_target for analysis in analyses),
                unanalyzed=sum(analysis.unanalyzed for analysis in analyses),
            ),
            items=[_overview_item(analysis) for analysis in page],
            total=len(ordered),
            page=query.page,
            page_size=query.page_size,
        )

    async def trend(
        self,
        workspace_id: str,
        query: TargetOverviewQuery,
    ) -> TargetTrendResponse:
        """Return a zero-filled target trend using the documented per-state times."""
        analyses = await self._analyses(workspace_id, query.window, query.targets)
        starts = bucket_starts(query.window)
        totals: dict[date, dict[TargetState, int]] = {
            start: {state: 0 for state in TARGET_STATES} for start in starts
        }
        by_target: dict[date, dict[str, dict[TargetState, int]]] = {
            start: {
                analysis.target.id: {state: 0 for state in TARGET_STATES} for analysis in analyses
            }
            for start in starts
        }
        for analysis in analyses:
            for entry in analysis.entries:
                if entry.state not in query.states:
                    continue
                moment = entry.attributed_at if entry.state != "unanalyzed" else entry.created_at
                if moment is None:
                    continue
                local_day = as_shanghai(moment).date()
                if not query.window.start <= local_day <= query.window.end:
                    continue
                start = bucket_start(local_day, query.window.grain)
                if start not in totals:
                    continue
                totals[start][entry.state] += 1
                by_target[start][analysis.target.id][entry.state] += 1
        return TargetTrendResponse(
            window=_window_dto(query.window),
            grain=query.window.grain,
            buckets=[
                TargetTrendBucket(
                    bucket=start,
                    label=bucket_label(start, query.window.grain),
                    attributed=totals[start]["attributed"],
                    non_target=totals[start]["nonTarget"],
                    unanalyzed=totals[start]["unanalyzed"],
                    by_target=[
                        TargetTrendByTarget(
                            target_id=analysis.target.id,
                            object_type=analysis.target.object_type,
                            object_name=analysis.target.object_name,
                            attributed=by_target[start][analysis.target.id]["attributed"],
                            non_target=by_target[start][analysis.target.id]["nonTarget"],
                            unanalyzed=by_target[start][analysis.target.id]["unanalyzed"],
                        )
                        for analysis in analyses
                    ],
                )
                for start in starts
            ],
            meta=TargetTrendMeta(bucket_policy=BUCKET_POLICY),
        )

    async def cases(
        self,
        workspace_id: str,
        query: TargetOverviewQuery,
    ) -> TargetCaseListResponse:
        """Return one filtered, newest-first page of potential case rows."""
        analyses = await self._analyses(workspace_id, query.window, query.targets)
        object_filter = frozenset(query.objects)
        rows = [
            entry
            for analysis in analyses
            for entry in analysis.entries
            if entry.state in query.states and (not object_filter or entry.source in object_filter)
        ]
        rows.sort(
            key=lambda entry: (
                -entry.created_at.timestamp(),
                entry.bad_case_id,
                entry.target.object_name.casefold(),
                entry.version,
                entry.target.id,
            ),
        )
        page_start = (query.page - 1) * query.page_size
        page = rows[page_start : page_start + query.page_size]
        return TargetCaseListResponse(
            items=[_case_item(entry) for entry in page],
            total=len(rows),
            page=query.page,
            page_size=query.page_size,
        )

    async def detail(
        self,
        workspace_id: str,
        target_id: str,
        query: TargetOverviewQuery,
    ) -> TargetDetailResponse:
        """Return one target's selected-version analysis; unknown targets are 404."""
        analyses = await self._analyses(workspace_id, query.window, (target_id,))
        analysis = next(
            (item for item in analyses if item.target.id == target_id),
            None,
        )
        if analysis is None:
            raise AppError(
                status_code=404,
                code=ErrorCode.TARGET_NOT_FOUND,
                message="evolution target does not exist",
            )
        selected = _selected_versions(analysis, query.versions, query.version_limit)
        selected_set = frozenset(selected)
        entries = [entry for entry in analysis.entries if entry.version in selected_set]
        by_version = [
            _version_row(
                version,
                [entry for entry in entries if entry.version == version],
                analysis.version_labels.get(version),
            )
            for version in selected
        ]
        sources: dict[str, list[TargetCaseEntry]] = defaultdict(list)
        for entry in entries:
            sources[entry.source].append(entry)
        by_source = sorted(
            (
                TargetDetailSource(
                    source=source,
                    total=len(source_entries),
                    distinct_cases=len({entry.bad_case_id for entry in source_entries}),
                )
                for source, source_entries in sources.items()
            ),
            key=lambda row: (-row.total, row.source.casefold(), row.source),
        )
        return TargetDetailResponse(
            target=TargetDetailTarget(
                target_id=analysis.target.id,
                object_type=analysis.target.object_type,
                object_name=analysis.target.object_name,
                default_ref=analysis.target.default_ref,
                versions=list(analysis.versions),
                version_options=_version_options(analysis),
            ),
            stats=TargetDetailStats(
                sessions=len(
                    {
                        session_id
                        for version in selected
                        for session_id in analysis.version_sessions.get(version, frozenset())
                    },
                ),
                potential=len(entries),
                distinct_cases=len({entry.bad_case_id for entry in entries}),
                versions=len(selected),
            ),
            by_version=by_version,
            by_source=by_source,
        )

    async def _analyses(
        self,
        workspace_id: str,
        window: Window,
        target_ids: tuple[str, ...],
    ) -> tuple[TargetAnalysis, ...]:
        """Evaluate every enabled in-scope target against the shared matcher."""
        targets = await self._targets.list(
            enabled_only=True,
            workspace_ids=(workspace_id,),
        )
        if target_ids:
            wanted = frozenset(target_ids)
            targets = tuple(target for target in targets if target.id in wanted)
        if not targets:
            return ()
        window_start, window_end = window_day_boundaries(window.start, window.end)
        facts = await self._repository.list_window_cases(
            workspace_id=workspace_id,
            window_start=window_start,
            window_end=window_end,
        )
        default_labels = {
            target.id: _build_version_labels(target.default_ref, (), ()) for target in targets
        }
        if not facts:
            return tuple(
                TargetAnalysis(
                    target=target,
                    versions=default_labels[target.id][0],
                    session_ids=frozenset(),
                    entries=(),
                    version_sessions={
                        version: frozenset() for version in default_labels[target.id][0]
                    },
                    version_labels=default_labels[target.id][1],
                )
                for target in targets
            )
        facts_by_id = {fact.bad_case_id: fact for fact in facts}
        session_ids = tuple(sorted({fact.session_id for fact in facts}))
        analyses = await asyncio.gather(
            *(
                self._analyse_target(
                    target,
                    workspace_id=workspace_id,
                    session_ids=session_ids,
                    facts_by_id=facts_by_id,
                    window_start=window_start,
                    window_end=window_end,
                )
                for target in targets
            ),
        )
        return tuple(analyses)

    async def _analyse_target(
        self,
        target: EvolutionTargetRecord,
        *,
        workspace_id: str,
        session_ids: tuple[str, ...],
        facts_by_id: dict[str, WindowCaseFact],
        window_start: datetime,
        window_end: datetime,
    ) -> TargetAnalysis:
        """Call the matcher per canonical version and project the included rows."""
        observed = await self._repository.list_object_versions(
            session_ids,
            object_type=target.object_type,
            object_name=target.object_name,
        )
        runs = await self._repository.list_target_runs(
            workspace_id=workspace_id,
            object_type=target.object_type,
            object_name=target.object_name,
            limit=RUN_VERSION_LOOKBACK,
        )
        versions, labels = _build_version_labels(target.default_ref, observed, runs)
        associated_sessions: set[str] = set()
        version_sessions: dict[str, frozenset[str]] = {}
        resolved = await asyncio.gather(
            *(self._resolve_version(target, version) for version in versions),
        )
        entries: list[TargetCaseEntry] = []
        unresolved_versions: set[str] = set()
        for version, resolution in zip(versions, resolved, strict=True):
            if resolution is None:
                # Content is the only identity source: keep the observed version
                # visible but never fall back to tag matching.
                unresolved_versions.add(version)
                version_sessions[version] = frozenset()
                continue
            label = labels[version]
            association, match = await self._evaluate_resolved(
                target,
                version,
                resolution,
                workspace_id=workspace_id,
                window_start=window_start,
                window_end=window_end,
            )
            associated_sessions.update(session.session_id for session in association.sessions)
            version_sessions[version] = frozenset(
                session.session_id for session in association.sessions
            )
            if not match.included:
                continue
            links = await self._repository.list_attributions(
                workspace_id=workspace_id,
                object_type=target.object_type,
                object_name=target.object_name,
                case_ids=tuple(item.bad_case_id for item in match.included),
            )
            newest = _newest_link_by_case(links, label.aliases)
            for item in match.included:
                fact = facts_by_id.get(item.bad_case_id)
                if fact is None:
                    continue
                link = newest.get(item.bad_case_id)
                entries.append(
                    _entry(
                        item,
                        target=target,
                        version=version,
                        display_version=label.display,
                        fact=fact,
                        link=link,
                    ),
                )
        return TargetAnalysis(
            target=target,
            versions=versions,
            session_ids=frozenset(associated_sessions),
            entries=tuple(entries),
            version_sessions=version_sessions,
            unresolved_versions=frozenset(unresolved_versions),
            version_labels=labels,
        )

    async def _resolve_version(
        self,
        target: EvolutionTargetRecord,
        version: str,
    ) -> ResolvedTargetVersion | None:
        """Resolve one version with a short timeout and a cached failure result."""
        key = (target.object_type, target.repo_url, target.sub_dir, version)
        now = time.monotonic()
        failed_at = self._failed_versions.get(key)
        if failed_at is not None:
            if now - failed_at < self._failure_ttl:
                return None
            self._failed_versions.pop(key, None)
        try:
            async with self._resolve_slots:
                return await asyncio.wait_for(
                    self._resolver.resolve(
                        object_type=target.object_type,
                        repo_url=target.repo_url,
                        sub_dir=target.sub_dir,
                        version=version,
                    ),
                    timeout=self._resolve_timeout,
                )
        except TimeoutError:
            self._remember_failure(key, now)
            return None
        except AppError as error:
            if error.code is not ErrorCode.TARGET_CONTENT_UNRESOLVED:
                raise
            self._remember_failure(key, now)
            return None

    def _remember_failure(self, key: tuple[str, str, str, str], now: float) -> None:
        """Keep one failed resolution for a bounded TTL so retries fail fast."""
        self._failed_versions[key] = now
        self._failed_versions.move_to_end(key)
        while len(self._failed_versions) > OVERVIEW_FAILURE_CACHE_SIZE:
            self._failed_versions.popitem(last=False)

    async def _evaluate(
        self,
        target: EvolutionTargetRecord,
        version: str,
        *,
        workspace_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[SessionAssociation, PotentialMatch] | None:
        """Resolve one version then run the shared matcher, or skip it."""
        resolved = await self._resolve_version(target, version)
        if resolved is None:
            return None
        return await self._evaluate_resolved(
            target,
            version,
            resolved,
            workspace_id=workspace_id,
            window_start=window_start,
            window_end=window_end,
        )

    async def _evaluate_resolved(
        self,
        target: EvolutionTargetRecord,
        version: str,
        resolved: ResolvedTargetVersion,
        *,
        workspace_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[SessionAssociation, PotentialMatch]:
        """Run the shared matcher for one already-resolved target version."""
        condition = MatchCondition(
            workspace_id=workspace_id,
            target_type=target.object_type,
            target_name=target.object_name,
            target_version=resolved.target_version,
            target_revision=resolved.target_revision,
            window_start=window_start,
            window_end=window_end,
        )
        association = await self._matcher.associated_sessions(condition)
        match = await self._matcher.potential_cases(condition, association, self._policy)
        return association, match


def _selected_versions(
    analysis: TargetAnalysis,
    requested: tuple[str, ...],
    version_limit: int,
) -> tuple[str, ...]:
    """Resolve the detail card's explicit or newest-N version scope.

    A requested value matches the canonical key or any persisted alias, so old
    URLs that still carry a ref (``main``) keep filtering after the display
    identity moves to the digest.
    """
    if requested:
        matches: list[str] = []
        for value in requested:
            for version in analysis.versions:
                if version in matches:
                    continue
                label = analysis.version_labels.get(version)
                aliases = label.aliases if label is not None else frozenset()
                if value == version or value in aliases:
                    matches.append(version)
        return tuple(matches)
    if version_limit == 0:
        return analysis.versions
    return analysis.versions[:version_limit]


def _entry(
    item: PotentialCase,
    *,
    target: EvolutionTargetRecord,
    version: str,
    display_version: str,
    fact: WindowCaseFact,
    link: AttributionLinkRecord | None,
) -> TargetCaseEntry:
    """Combine one matcher row with the case facts and its newest attribution."""
    state = _state(link)
    return TargetCaseEntry(
        bad_case_id=item.bad_case_id,
        target=target,
        version=version,
        session_id=fact.session_id,
        source=fact.source,
        bad_case_type=fact.bad_case_type,
        title=fact.title,
        created_at=fact.created_at,
        state=state,
        attribution_id=link.attribution_id if link is not None else None,
        category=_category(link) if state == "attributed" else None,
        attributed_at=link.created_at if link is not None else None,
        display_version=display_version,
    )


def _version_options(analysis: TargetAnalysis) -> list[TargetVersionOption]:
    """Project one analysis's version labels into the wire contract."""
    options: list[TargetVersionOption] = []
    for version in analysis.versions:
        label = analysis.version_labels.get(version)
        options.append(
            TargetVersionOption(
                version=version,
                ref=label.ref if label is not None else None,
                commit=label.commit if label is not None else None,
            ),
        )
    return options


def _overview_item(analysis: TargetAnalysis) -> TargetOverviewItem:
    """Map one target analysis to its list contract."""
    return TargetOverviewItem(
        target_id=analysis.target.id,
        object_type=analysis.target.object_type,
        object_name=analysis.target.object_name,
        versions=list(analysis.versions),
        version_options=_version_options(analysis),
        sessions=analysis.sessions,
        potential=analysis.potential,
        attributed=analysis.attributed,
        non_target=analysis.non_target,
        unanalyzed=analysis.unanalyzed,
        evolvable=analysis.evolvable,
    )


def _case_item(entry: TargetCaseEntry) -> TargetCaseItem:
    """Map one projected potential row to the case-list contract."""
    return TargetCaseItem(
        bad_case_id=entry.bad_case_id,
        object_type=entry.target.object_type,
        object_name=entry.target.object_name,
        object_version=entry.display_version or entry.version,
        source=entry.source,
        state=entry.state,
        bad_case_type=cast(Literal["self", "discovery"], entry.bad_case_type),
        title=entry.title,
        created_at=entry.created_at,
        session_id=entry.session_id,
        attribution_id=entry.attribution_id,
        category=entry.category,
    )


def _version_row(
    version: str,
    entries: Sequence[TargetCaseEntry],
    label: TargetVersionLabel | None = None,
) -> TargetDetailVersion:
    """Aggregate one selected version's potential rows into three counts."""
    return TargetDetailVersion(
        version=version,
        ref=label.ref if label is not None else None,
        commit=label.commit if label is not None else None,
        potential=len(entries),
        attributed=sum(1 for entry in entries if entry.state == "attributed"),
        non_target=sum(1 for entry in entries if entry.state == "nonTarget"),
        unanalyzed=sum(1 for entry in entries if entry.state == "unanalyzed"),
    )


def _window_dto(window: Window) -> OverviewWindow:
    """Map the resolved inclusive window into its wire contract."""
    return OverviewWindow(date_from=window.start, date_to=window.end)
