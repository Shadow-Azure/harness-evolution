"""Multi-attribution, cache, and run-candidate persistence."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import aliased

from app.db.base import Database
from app.db.external_contract import read_only_guard
from app.db.models.domain import (
    agent_events,
    agents,
    bad_case_analysis,
    bad_cases,
    probe_reports,
)
from app.db.models.evolution import (
    EvolutionRunCandidateRecord,
    evolution_run_candidates,
    record_from_evolution_run_candidate,
)
from app.utils.time import as_shanghai

_QUERY_CHUNK = 500

OrderState = Literal["comparable", "unknown"]
IncludedReason = Literal[
    "self_report",
    "after_object",
    "both",
    "policy_excluded",
    "order_unknown",
]

ORDER_STATES: frozenset[str] = frozenset({"comparable", "unknown"})
INCLUDED_REASONS: frozenset[str] = frozenset(
    {"self_report", "after_object", "both", "policy_excluded", "order_unknown"},
)


def attribution_cache_key(
    workspace_id: str,
    bad_case_id: str,
    probe_type: str,
    probe_object: str,
    object_version: str | None,
    policy_version: str,
    attribution_engine: str,
) -> str:
    """Return the stable seven-part attribution cache key.

    The fields are concatenated in the order above with no separator, and a
    missing object version collapses to the empty string. PostgreSQL-style
    delimiter ambiguity does not matter here because every caller builds the
    tuple from the persisted columns.
    """
    parts = (
        workspace_id,
        bad_case_id,
        probe_type,
        probe_object,
        object_version or "",
        policy_version,
        attribution_engine,
    )
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProbeWrite:
    """Database-neutral probe payload used by the atomic cache upsert."""

    probe_id: str
    workspace_id: str
    session_id: str
    bad_case_id: str
    probe_type: str
    probe_object: str
    object_version: str | None
    attribute_type: str | None
    conclusion: str
    confidence: float
    probe_description: str
    probe_analysis: str
    policy_version: str
    attribution_engine: str
    created_run_id: str | None
    created_at: datetime
    updated_at: datetime
    report_schema_version: str | None = None
    report_payload: Mapping[str, object] | None = None
    execution_manifest: Mapping[str, object] | None = None
    execution_manifest_hash: str | None = None

    def __post_init__(self) -> None:
        """Reject malformed identities and normalize an empty object version."""
        for field_name in ("probe_id", "workspace_id", "bad_case_id", "session_id"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")
        if self.probe_type not in {"skill", "agent", "knowledge"}:
            raise ValueError(f"unknown probe_type: {self.probe_type}")
        if self.conclusion not in {"attributed", "non_target", "inconclusive"}:
            raise ValueError(f"unknown conclusion: {self.conclusion}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0, 1]: {self.confidence}")
        if self.object_version == "":
            object.__setattr__(self, "object_version", None)

    @property
    def cache_key(self) -> str:
        """Derive the cache key from the persisted identity fields."""
        if self.execution_manifest_hash is not None:
            return self.execution_manifest_hash
        return attribution_cache_key(
            self.workspace_id,
            self.bad_case_id,
            self.probe_type,
            self.probe_object,
            self.object_version,
            self.policy_version,
            self.attribution_engine,
        )


def _chunks(values: Sequence[str], size: int = _QUERY_CHUNK) -> Iterator[tuple[str, ...]]:
    """Yield stable identifier chunks so one IN predicate stays bounded."""
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])


@dataclass(frozen=True, slots=True)
class ProbeCacheRecord:
    """One cached probe row keyed by its seven-part identity."""

    probe_id: str
    workspace_id: str
    session_id: str
    probe_type: str
    probe_object: str
    object_version: str | None
    attribute_type: str | None
    conclusion: str
    confidence: float
    probe_description: str
    probe_analysis: str
    policy_version: str
    attribution_engine: str
    cache_key: str
    report_schema_version: str | None
    report_payload: Mapping[str, object] | None
    execution_manifest: Mapping[str, object] | None
    execution_manifest_hash: str | None
    created_run_id: str | None
    last_reused_run_id: str | None
    reused_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BadCaseEvidenceRecord:
    """The bad-case fields a pure attribution engine may use."""

    bad_case_id: str
    session_id: str
    bad_case_type: str
    title: str
    description: str
    metadata: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class KnowledgeEvidenceRecord:
    """One knowledge document trigger found in a case's root session."""

    session_id: str
    document_id: str | None
    document_revision: str | None
    source_path: str | None
    retrieval_kind: str | None


@dataclass(frozen=True, slots=True)
class AttributionRecord:
    """One case-to-probe attribution joined with its probe detail."""

    bad_case_id: str
    probe_id: str
    workspace_id: str
    session_id: str
    probe_type: str
    probe_object: str
    object_version: str | None
    attribute_type: str | None
    conclusion: str
    confidence: float
    probe_description: str
    probe_analysis: str
    policy_version: str
    attribution_engine: str
    cache_key: str | None
    report_schema_version: str | None
    report_payload: Mapping[str, object] | None
    execution_manifest: Mapping[str, object] | None
    execution_manifest_hash: str | None
    created_run_id: str | None
    last_reused_run_id: str | None
    reused_count: int
    analysis_status: str | None
    analysis_result: object | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CandidateTriggerRecord:
    """One attribution's newest candidate trigger coordinates.

    ``order_state`` records whether prepare could compare the two trigger
    points at all; the wall-clock and coordinate columns are kept raw so the
    read service can apply the documented time-first comparison.
    """

    order_state: str
    object_trigger_at: datetime | None
    case_trigger_at: datetime | None
    object_trigger_tree_index: int | None
    object_trigger_event_index: int | None
    case_trigger_tree_index: int | None
    case_trigger_event_index: int | None


@dataclass(frozen=True, slots=True)
class CandidateWrite:
    """Database-neutral run-candidate snapshot used by the idempotent upsert."""

    id: str
    run_id: str
    workspace_id: str
    session_id: str
    bad_case_id: str
    order_state: OrderState
    included: bool
    included_reason: IncludedReason
    created_at: datetime
    object_trigger_agent_id: str | None = None
    object_trigger_event_index: int | None = None
    object_trigger_at: datetime | None = None
    case_trigger_agent_id: str | None = None
    case_trigger_event_index: int | None = None
    case_trigger_at: datetime | None = None
    probe_id: str | None = None
    is_cached: bool = False

    def __post_init__(self) -> None:
        """Reject closed-set values before a dialect statement is compiled."""
        if self.order_state not in ORDER_STATES:
            raise ValueError(f"unknown order_state: {self.order_state}")
        if self.included_reason not in INCLUDED_REASONS:
            raise ValueError(f"unknown included_reason: {self.included_reason}")


def _text(value: object) -> str | None:
    """Preserve a non-empty string without coercing arbitrary database values."""
    return value if isinstance(value, str) and value else None


def _mapping(value: object) -> Mapping[str, object] | None:
    """Copy one JSON object while rejecting arrays and scalar drift."""
    return dict(value) if isinstance(value, Mapping) else None


def _row_attribution(mapping: RowMapping) -> AttributionRecord:
    """Convert one joined attribution mapping into a boundary record."""
    return AttributionRecord(
        bad_case_id=mapping["bad_case_id"],
        probe_id=mapping["probe_id"],
        workspace_id=mapping["workspace_id"],
        session_id=mapping["session_id"],
        probe_type=mapping["probe_type"],
        probe_object=mapping["probe_object"],
        object_version=_text(mapping["object_version"]),
        attribute_type=_text(mapping["attribute_type"]),
        conclusion=mapping["conclusion"],
        confidence=float(mapping["confidence"]),
        probe_description=mapping["probe_description"],
        probe_analysis=mapping["probe_analysis"],
        policy_version=mapping["policy_version"],
        attribution_engine=mapping["attribution_engine"],
        cache_key=_text(mapping["cache_key"]),
        report_schema_version=_text(mapping["report_schema_version"]),
        report_payload=_mapping(mapping["report_payload"]),
        execution_manifest=_mapping(mapping["execution_manifest"]),
        execution_manifest_hash=_text(mapping["execution_manifest_hash"]),
        created_run_id=_text(mapping["created_run_id"]),
        last_reused_run_id=_text(mapping["last_reused_run_id"]),
        reused_count=int(mapping["reused_count"]),
        analysis_status=_text(mapping["analysis_status"]),
        analysis_result=mapping["analysis_result"],
        created_at=as_shanghai(mapping["created_at"]),
        updated_at=as_shanghai(mapping["updated_at"]),
    )


def _row_probe_cache(mapping: RowMapping) -> ProbeCacheRecord:
    """Convert one probe-only mapping into the cache boundary record."""
    return ProbeCacheRecord(
        probe_id=mapping["probe_id"],
        workspace_id=mapping["workspace_id"],
        session_id=mapping["session_id"],
        probe_type=mapping["probe_type"],
        probe_object=mapping["probe_object"],
        object_version=_text(mapping["object_version"]),
        attribute_type=_text(mapping["attribute_type"]),
        conclusion=mapping["conclusion"],
        confidence=float(mapping["confidence"]),
        probe_description=mapping["probe_description"],
        probe_analysis=mapping["probe_analysis"],
        policy_version=mapping["policy_version"],
        attribution_engine=mapping["attribution_engine"],
        cache_key=mapping["cache_key"],
        report_schema_version=_text(mapping["report_schema_version"]),
        report_payload=_mapping(mapping["report_payload"]),
        execution_manifest=_mapping(mapping["execution_manifest"]),
        execution_manifest_hash=_text(mapping["execution_manifest_hash"]),
        created_run_id=_text(mapping["created_run_id"]),
        last_reused_run_id=_text(mapping["last_reused_run_id"]),
        reused_count=int(mapping["reused_count"]),
        created_at=as_shanghai(mapping["created_at"]),
        updated_at=as_shanghai(mapping["updated_at"]),
    )


class AttributionRepository:
    """Write attributions atomically and read one case's current attributions."""

    def __init__(self, database: Database) -> None:
        """Bind this repository to one application database."""
        self._database = database

    async def upsert_probe(self, write: ProbeWrite) -> str:
        """Insert a probe or update the row that already owns its cache key.

        The conflict target is the unique ``cache_key`` index, so concurrent
        writers of the same seven-part identity converge on one ``probe_id``
        without a read-before-write check. The existing probe id wins; every
        mutable conclusion field is refreshed.
        """
        values, updates = self._probe_upsert_parts(write)
        statement = self._probe_upsert_statement(values, updates)
        async with self._database.transaction() as session:
            await session.execute(statement)
            return await self._select_probe_id(session, write.cache_key)

    async def get_probe_by_cache_key(self, cache_key: str) -> ProbeCacheRecord | None:
        """Return the one probe owning a cache key, or ``None`` on a miss."""
        statement = select(probe_reports).where(probe_reports.c.cache_key == cache_key).limit(1)
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _row_probe_cache(row) if row is not None else None

    async def write_probe_and_link(
        self,
        write: ProbeWrite,
        run_id: str,
        now: datetime,
    ) -> str:
        """Write a fresh probe, its case link, and its candidate pointer atomically.

        The candidate snapshot must already exist: prepare inserts it in the
        potential step, and a missing row means the attribution step is out of
        order. Rolling the probe and link back keeps the cache and the run
        snapshot consistent after that programming error.

        Args:
            write: Dialect-neutral probe payload.
            run_id: Run whose candidate row receives the probe pointer.
            now: Link timestamp shared by the three writes.

        Returns:
            The probe id that owns the cache key after the upsert.

        Raises:
            LookupError: When the run has no candidate row for this bad case.
        """
        values, updates = self._probe_upsert_parts(write)
        statement = self._probe_upsert_statement(values, updates)
        async with self._database.transaction() as session:
            await session.execute(statement)
            probe_id = await self._select_probe_id(session, write.cache_key)
            await session.execute(self._link_statement(write.bad_case_id, probe_id, now))
            result = await session.execute(
                self._candidate_update_statement(
                    run_id,
                    write.bad_case_id,
                    probe_id,
                    is_cached=False,
                ),
            )
            if int(getattr(result, "rowcount", 0) or 0) == 0:
                await self._require_candidate(session, run_id, write.bad_case_id)
        return probe_id

    async def reuse_probe_and_link(
        self,
        probe_id: str,
        run_id: str,
        bad_case_id: str,
        now: datetime,
    ) -> bool:
        """Count one cache hit and link it to the run in one transaction.

        Args:
            probe_id: Existing probe selected by cache key.
            run_id: Run that consumed the cached conclusion.
            bad_case_id: Case whose candidate row receives the pointer.
            now: Reuse and link timestamp.

        Returns:
            ``True`` when this run advanced ``reused_count``; ``False`` for a
            repeated hit from the same run.

        Raises:
            LookupError: When the run has no candidate row for this bad case.
        """
        async with self._database.transaction() as session:
            result = await session.execute(self._reuse_statement(probe_id, run_id, now))
            await session.execute(self._link_statement(bad_case_id, probe_id, now))
            updated = await session.execute(
                self._candidate_update_statement(
                    run_id,
                    bad_case_id,
                    probe_id,
                    is_cached=True,
                ),
            )
            if int(getattr(updated, "rowcount", 0) or 0) == 0:
                await self._require_candidate(session, run_id, bad_case_id)
        return int(getattr(result, "rowcount", 0) or 0) > 0

    async def linked_probe_ids(self, run_id: str) -> dict[str, str]:
        """Return the candidates of one run that already carry a probe pointer."""
        statement = select(
            evolution_run_candidates.c.bad_case_id,
            evolution_run_candidates.c.probe_id,
        ).where(
            evolution_run_candidates.c.run_id == run_id,
            evolution_run_candidates.c.probe_id.is_not(None),
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).all()
        return {str(row[0]): str(row[1]) for row in rows}

    async def list_clusterable_probes(
        self,
        run_id: str,
    ) -> tuple[tuple[str, str, str], ...]:
        """Return ``(probe_id, attribute_type, bad_case_id)`` for attributed rows.

        Clustering only consumes included candidates whose probe conclusion is
        ``attributed``; ``non_target`` rows stay visible in attribution but never
        reach a cluster.
        """
        statement = (
            select(
                evolution_run_candidates.c.probe_id,
                probe_reports.c.attribute_type,
                evolution_run_candidates.c.bad_case_id,
            )
            .select_from(
                evolution_run_candidates.join(
                    probe_reports,
                    probe_reports.c.probe_id == evolution_run_candidates.c.probe_id,
                ),
            )
            .where(
                evolution_run_candidates.c.run_id == run_id,
                evolution_run_candidates.c.included.is_(True),
                probe_reports.c.conclusion == "attributed",
            )
            .order_by(evolution_run_candidates.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).all()
        return tuple(
            (str(row[0]), str(row[1]), str(row[2]))
            for row in rows
            if row[0] is not None and row[1] is not None
        )

    async def list_clusterable_probe_ids(self, run_id: str) -> tuple[str, ...]:
        """Return included, attributed probes in stable bad-case order.

        ``non_target`` and policy-excluded candidates never reach the cluster
        step, so this is the exact input projection m10-04 should consume.
        """
        statement = (
            select(evolution_run_candidates.c.probe_id)
            .select_from(
                evolution_run_candidates.join(
                    probe_reports,
                    probe_reports.c.probe_id == evolution_run_candidates.c.probe_id,
                ),
            )
            .where(
                evolution_run_candidates.c.run_id == run_id,
                evolution_run_candidates.c.included.is_(True),
                probe_reports.c.conclusion == "attributed",
            )
            .order_by(evolution_run_candidates.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows: Sequence[object] = (await session.execute(statement)).scalars().all()
        return tuple(str(row) for row in rows if row is not None)

    async def load_bad_case_evidence(
        self,
        case_ids: Sequence[str],
    ) -> dict[str, BadCaseEvidenceRecord]:
        """Load titles, descriptions, and metadata for a bounded case set."""
        found: dict[str, BadCaseEvidenceRecord] = {}
        for chunk in _chunks(tuple(dict.fromkeys(case_ids))):
            statement = select(
                bad_cases.c.bad_case_id,
                bad_cases.c.bad_case_session_id,
                bad_cases.c.bad_case_type,
                bad_cases.c.title,
                bad_cases.c.bad_case_description,
                bad_cases.c.meta_data,
            ).where(bad_cases.c.bad_case_id.in_(chunk))
            async with self._database.session() as session:
                rows = (await session.execute(statement)).mappings().all()
            for row in rows:
                metadata = row["meta_data"]
                found[str(row["bad_case_id"])] = BadCaseEvidenceRecord(
                    bad_case_id=str(row["bad_case_id"]),
                    session_id=str(row["bad_case_session_id"]),
                    bad_case_type=str(row["bad_case_type"]),
                    title=str(row["title"]),
                    description=str(row["bad_case_description"]),
                    metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
                )
        return found

    async def load_knowledge_evidence(
        self,
        session_ids: Sequence[str],
    ) -> dict[str, tuple[KnowledgeEvidenceRecord, ...]]:
        """Load knowledge document triggers for a bounded set of root sessions."""
        grouped: dict[str, list[KnowledgeEvidenceRecord]] = {}
        for chunk in _chunks(tuple(dict.fromkeys(session_ids))):
            statement = (
                select(
                    agents.c.root_session_id,
                    agent_events.c.document_id,
                    agent_events.c.document_revision,
                    agent_events.c.source_path,
                    agent_events.c.retrieval_kind,
                )
                .select_from(agent_events)
                .join(agents, agents.c.id == agent_events.c.agent_id)
                .where(
                    agents.c.root_session_id.in_(chunk),
                    agent_events.c.kind == "knowledge",
                )
                .order_by(
                    agents.c.root_session_id,
                    agents.c.tree_index,
                    agent_events.c.event_index,
                )
            )
            async with self._database.session() as session:
                rows = (await session.execute(statement)).mappings().all()
            for row in rows:
                session_id = str(row["root_session_id"])
                event = KnowledgeEvidenceRecord(
                    session_id=session_id,
                    document_id=_text(row["document_id"]),
                    document_revision=_text(row["document_revision"]),
                    source_path=_text(row["source_path"]),
                    retrieval_kind=_text(row["retrieval_kind"]),
                )
                bucket = grouped.setdefault(session_id, [])
                identity = (event.document_id, event.document_revision, event.source_path)
                if any(
                    (item.document_id, item.document_revision, item.source_path) == identity
                    for item in bucket
                ):
                    continue
                bucket.append(event)
        return {session_id: tuple(events) for session_id, events in grouped.items()}

    def _probe_upsert_parts(
        self,
        write: ProbeWrite,
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Build the insert and conflict-update payloads for one probe."""
        values: dict[str, object] = {
            "probe_id": write.probe_id,
            "workspace_id": write.workspace_id,
            "session_id": write.session_id,
            "probe_type": write.probe_type,
            "probe_object": write.probe_object,
            "object_version": write.object_version,
            "attribute_type": write.attribute_type,
            "conclusion": write.conclusion,
            "confidence": write.confidence,
            "probe_description": write.probe_description,
            "probe_analysis": write.probe_analysis,
            "policy_version": write.policy_version,
            "attribution_engine": write.attribution_engine,
            "cache_key": write.cache_key,
            "report_schema_version": write.report_schema_version,
            "report_payload": (
                dict(write.report_payload) if write.report_payload is not None else None
            ),
            "execution_manifest": (
                dict(write.execution_manifest) if write.execution_manifest is not None else None
            ),
            "execution_manifest_hash": write.execution_manifest_hash,
            "created_run_id": write.created_run_id,
            "last_reused_run_id": None,
            "reused_count": 0,
            "created_at": write.created_at,
            "updated_at": write.updated_at,
        }
        updates: dict[str, object] = {
            "attribute_type": write.attribute_type,
            "conclusion": write.conclusion,
            "confidence": write.confidence,
            "probe_description": write.probe_description,
            "probe_analysis": write.probe_analysis,
            "policy_version": write.policy_version,
            "attribution_engine": write.attribution_engine,
            "report_schema_version": write.report_schema_version,
            "report_payload": (
                dict(write.report_payload) if write.report_payload is not None else None
            ),
            "execution_manifest": (
                dict(write.execution_manifest) if write.execution_manifest is not None else None
            ),
            "execution_manifest_hash": write.execution_manifest_hash,
            "updated_at": write.updated_at,
        }
        if write.created_run_id is not None:
            updates["created_run_id"] = write.created_run_id
        return values, updates

    def _probe_upsert_statement(
        self,
        values: dict[str, object],
        updates: dict[str, object],
    ) -> Any:
        """Compile the dialect-specific atomic probe upsert."""
        dialect = self._database.dialect
        if dialect == "sqlite":
            return (
                sqlite_insert(probe_reports)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[probe_reports.c.cache_key],
                    set_=updates,
                )
            )
        if dialect == "mysql":
            return (
                mysql_insert(probe_reports)
                .values(**values)
                .on_duplicate_key_update(
                    **updates,
                )
            )
        raise ValueError(f"unsupported database dialect for attribution upsert: {dialect}")

    async def _select_probe_id(self, session: Any, cache_key: str) -> str:
        """Read the winning probe id after an insert-or-update statement."""
        return str(
            (
                await session.execute(
                    select(probe_reports.c.probe_id).where(
                        probe_reports.c.cache_key == cache_key,
                    ),
                )
            ).scalar_one(),
        )

    def _link_statement(self, bad_case_id: str, probe_id: str, now: datetime) -> Any:
        """Compile the dialect-specific idempotent case-to-probe link."""
        values: dict[str, object] = {
            "bad_case_id": bad_case_id,
            "analysis_status": None,
            "probe_id": probe_id,
            "analysis_result": None,
            "updated_at": now,
        }
        dialect = self._database.dialect
        if dialect == "sqlite":
            return (
                sqlite_insert(bad_case_analysis)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[
                        bad_case_analysis.c.bad_case_id,
                        bad_case_analysis.c.probe_id,
                    ],
                    set_={"updated_at": now},
                )
            )
        if dialect == "mysql":
            return (
                mysql_insert(bad_case_analysis)
                .values(**values)
                .on_duplicate_key_update(updated_at=now)
            )
        raise ValueError(f"unsupported database dialect for attribution link: {dialect}")

    def _reuse_statement(self, probe_id: str, run_id: str, now: datetime) -> Any:
        """Compile one cache-hit counter update, at most once per run."""
        return (
            update(probe_reports)
            .where(
                probe_reports.c.probe_id == probe_id,
                (probe_reports.c.last_reused_run_id.is_(None))
                | (probe_reports.c.last_reused_run_id != run_id),
            )
            .values(
                reused_count=probe_reports.c.reused_count + 1,
                last_reused_run_id=run_id,
                updated_at=now,
            )
        )

    def _candidate_update_statement(
        self,
        run_id: str,
        bad_case_id: str,
        probe_id: str,
        *,
        is_cached: bool,
    ) -> Any:
        """Point one run candidate at the probe that now owns its conclusion."""
        return (
            update(evolution_run_candidates)
            .where(
                evolution_run_candidates.c.run_id == run_id,
                evolution_run_candidates.c.bad_case_id == bad_case_id,
            )
            .values(probe_id=probe_id, is_cached=is_cached)
        )

    async def _require_candidate(
        self,
        session: Any,
        run_id: str,
        bad_case_id: str,
    ) -> None:
        """Reject a no-op candidate update only when the row is really absent."""
        found = (
            await session.execute(
                select(evolution_run_candidates.c.id)
                .where(
                    evolution_run_candidates.c.run_id == run_id,
                    evolution_run_candidates.c.bad_case_id == bad_case_id,
                )
                .limit(1),
            )
        ).scalar_one_or_none()
        if found is None:
            raise LookupError(f"run candidate not found: {run_id}/{bad_case_id}")

    async def upsert_link(
        self,
        bad_case_id: str,
        probe_id: str,
        now: datetime,
    ) -> None:
        """Link a case and probe once, keeping legacy compatibility columns.

        V2 rows leave ``analysis_status`` / ``analysis_result`` empty: the probe
        conclusion is the single source of truth. A conflicting legacy row only
        refreshes ``updated_at`` so its historical status remains readable.
        """
        async with self._database.transaction() as session:
            await session.execute(self._link_statement(bad_case_id, probe_id, now))

    async def reuse(self, probe_id: str, run_id: str, now: datetime) -> int:
        """Record one cache hit, at most once per run.

        Returns:
            The number of updated rows: 0 for an unknown probe or a repeated hit
            from the same run, 1 when the counter advanced.
        """
        async with self._database.transaction() as session:
            result = await session.execute(self._reuse_statement(probe_id, run_id, now))
        return int(getattr(result, "rowcount", 0) or 0)

    @read_only_guard("bad_case_analysis,probe_reports")
    async def list_run_attributions(
        self,
        run_id: str,
    ) -> tuple[AttributionRecord, ...]:
        """Return every attribution linked to one run's candidate snapshot."""
        statement = (
            self._attribution_statement()
            .join(
                evolution_run_candidates,
                evolution_run_candidates.c.probe_id == probe_reports.c.probe_id,
            )
            .where(evolution_run_candidates.c.run_id == run_id)
            .order_by(probe_reports.c.updated_at.desc(), probe_reports.c.probe_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_row_attribution(row) for row in rows)

    @read_only_guard("bad_case_analysis,probe_reports")
    async def list_attributions(
        self,
        case_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[AttributionRecord, ...]:
        """Return one case's attributions in stable newest-first page order."""
        statement = (
            self._attribution_statement()
            .where(bad_case_analysis.c.bad_case_id == case_id)
            .order_by(probe_reports.c.updated_at.desc(), probe_reports.c.probe_id.desc())
            .offset(offset)
            .limit(limit)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_row_attribution(row) for row in rows)

    @read_only_guard("probe_reports")
    async def load_historical_probe_ids(
        self,
        session_ids: Sequence[str],
    ) -> dict[str, tuple[str, ...]]:
        """Batch-load stable historical report references for context bundles."""
        if not session_ids:
            return {}
        statement = (
            select(probe_reports.c.session_id, probe_reports.c.probe_id)
            .where(probe_reports.c.session_id.in_(tuple(dict.fromkeys(session_ids))))
            .order_by(
                probe_reports.c.session_id, probe_reports.c.created_at, probe_reports.c.probe_id
            )
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        grouped: dict[str, list[str]] = {}
        for row in rows:
            grouped.setdefault(str(row["session_id"]), []).append(str(row["probe_id"]))
        return {session_id: tuple(probe_ids) for session_id, probe_ids in grouped.items()}

    @read_only_guard("bad_case_analysis,probe_reports")
    async def count_links(self, case_id: str) -> int:
        """Count linked attributions, the pagination total rather than objects.

        Legacy rows without a probe cannot be projected as an ``AttributionItem``
        and are therefore excluded, keeping ``total`` equal to the reachable
        rows for a page.
        """
        statement = (
            select(func.count())
            .select_from(self._attribution_join())
            .where(bad_case_analysis.c.bad_case_id == case_id)
        )
        async with self._database.session() as session:
            return int((await session.execute(statement)).scalar_one())

    async def latest_candidate_trigger(
        self,
        probe_id: str,
    ) -> CandidateTriggerRecord | None:
        """Return the newest run candidate that pointed at one attribution.

        The coordinate lookup joins both trigger agents so the read service can
        compare ``(tree_index, event_index)`` when wall-clock times are not
        available on both sides. Candidates without a probe never match.
        """
        object_agent = aliased(agents)
        case_agent = aliased(agents)
        statement = (
            select(
                evolution_run_candidates.c.order_state,
                evolution_run_candidates.c.object_trigger_at,
                evolution_run_candidates.c.case_trigger_at,
                object_agent.c.tree_index.label("object_tree_index"),
                evolution_run_candidates.c.object_trigger_event_index,
                case_agent.c.tree_index.label("case_tree_index"),
                evolution_run_candidates.c.case_trigger_event_index,
            )
            .select_from(
                evolution_run_candidates.outerjoin(
                    object_agent,
                    object_agent.c.id == evolution_run_candidates.c.object_trigger_agent_id,
                ).outerjoin(
                    case_agent,
                    case_agent.c.id == evolution_run_candidates.c.case_trigger_agent_id,
                ),
            )
            .where(evolution_run_candidates.c.probe_id == probe_id)
            .order_by(
                evolution_run_candidates.c.created_at.desc(),
                evolution_run_candidates.c.id.desc(),
            )
            .limit(1)
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        return CandidateTriggerRecord(
            order_state=row["order_state"],
            object_trigger_at=(
                as_shanghai(row["object_trigger_at"])
                if row["object_trigger_at"] is not None
                else None
            ),
            case_trigger_at=(
                as_shanghai(row["case_trigger_at"]) if row["case_trigger_at"] is not None else None
            ),
            object_trigger_tree_index=row["object_tree_index"],
            object_trigger_event_index=row["object_trigger_event_index"],
            case_trigger_tree_index=row["case_tree_index"],
            case_trigger_event_index=row["case_trigger_event_index"],
        )

    @read_only_guard("bad_case_analysis,probe_reports")
    async def attribution_count(self, case_id: str) -> int:
        """Count distinct ``(probe_type, probe_object, object_version)`` rows."""
        distinct = (
            select(
                probe_reports.c.probe_type,
                probe_reports.c.probe_object,
                probe_reports.c.object_version,
            )
            .select_from(self._attribution_join())
            .where(bad_case_analysis.c.bad_case_id == case_id)
            .distinct()
            .subquery()
        )
        async with self._database.session() as session:
            count = (await session.execute(select(func.count()).select_from(distinct))).scalar_one()
        return int(count)

    @read_only_guard("bad_case_analysis,probe_reports")
    async def get_attribution(
        self,
        case_id: str,
        probe_id: str,
    ) -> AttributionRecord | None:
        """Return one attribution only when it is still linked to the case."""
        statement = (
            self._attribution_statement()
            .where(
                bad_case_analysis.c.bad_case_id == case_id,
                bad_case_analysis.c.probe_id == probe_id,
            )
            .limit(1)
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one_or_none()
        return _row_attribution(row) if row is not None else None

    def _attribution_join(self) -> Any:
        """Join the case link to its probe detail."""
        return bad_case_analysis.join(
            probe_reports,
            probe_reports.c.probe_id == bad_case_analysis.c.probe_id,
        )

    def _attribution_statement(self) -> Any:
        """Select probe detail plus the legacy compatibility columns."""
        return select(
            bad_case_analysis.c.bad_case_id,
            probe_reports,
            bad_case_analysis.c.analysis_status,
            bad_case_analysis.c.analysis_result,
        ).select_from(self._attribution_join())


class EvolutionRunCandidateRepository:
    """Persist the full run candidate snapshot, included and excluded rows."""

    def __init__(self, database: Database) -> None:
        """Bind this repository to one application database."""
        self._database = database

    async def upsert(self, write: CandidateWrite) -> None:
        """Insert a candidate or refresh the same ``(run, case)`` row."""
        statement = self._upsert_statement(write)
        async with self._database.transaction() as session:
            await session.execute(statement)

    async def upsert_many(self, writes: Sequence[CandidateWrite]) -> None:
        """Upsert one complete candidate snapshot in a single transaction.

        The ``(run_id, bad_case_id)`` conflict target makes a repeated prepare
        idempotent; one transaction keeps the snapshot all-or-nothing.

        Args:
            writes: Full candidate set for one run, included and excluded.
        """
        if not writes:
            return
        statements = [self._upsert_statement(write) for write in writes]
        async with self._database.transaction() as session:
            for statement in statements:
                await session.execute(statement)

    def _upsert_statement(self, write: CandidateWrite) -> Any:
        """Build the dialect-specific upsert statement for one candidate."""
        values: dict[str, object] = {
            "id": write.id,
            "run_id": write.run_id,
            "workspace_id": write.workspace_id,
            "session_id": write.session_id,
            "bad_case_id": write.bad_case_id,
            "object_trigger_agent_id": write.object_trigger_agent_id,
            "object_trigger_event_index": write.object_trigger_event_index,
            "object_trigger_at": write.object_trigger_at,
            "case_trigger_agent_id": write.case_trigger_agent_id,
            "case_trigger_event_index": write.case_trigger_event_index,
            "case_trigger_at": write.case_trigger_at,
            "order_state": write.order_state,
            "included": write.included,
            "included_reason": write.included_reason,
            "probe_id": write.probe_id,
            "is_cached": write.is_cached,
            "created_at": write.created_at,
        }
        updates: dict[str, object] = {
            key: value for key, value in values.items() if key not in {"id", "run_id", "created_at"}
        }
        dialect = self._database.dialect
        if dialect == "sqlite":
            return (
                sqlite_insert(evolution_run_candidates)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[
                        evolution_run_candidates.c.run_id,
                        evolution_run_candidates.c.bad_case_id,
                    ],
                    set_=updates,
                )
            )
        if dialect == "mysql":
            return (
                mysql_insert(evolution_run_candidates)
                .values(**values)
                .on_duplicate_key_update(**updates)
            )
        raise ValueError(f"unsupported database dialect for candidate upsert: {dialect}")

    async def list(self, run_id: str) -> tuple[EvolutionRunCandidateRecord, ...]:
        """Return every candidate of one run in stable bad-case order."""
        statement = (
            select(evolution_run_candidates)
            .where(evolution_run_candidates.c.run_id == run_id)
            .order_by(evolution_run_candidates.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(record_from_evolution_run_candidate(row) for row in rows)

    async def count(self, run_id: str) -> int:
        """Count persisted candidates so prepare can audit the full snapshot.

        Args:
            run_id: Evolution run whose candidate rows are counted.

        Returns:
            The number of candidate rows currently stored for the run.
        """
        statement = (
            select(func.count())
            .select_from(evolution_run_candidates)
            .where(evolution_run_candidates.c.run_id == run_id)
        )
        async with self._database.session() as session:
            count = (await session.execute(statement)).scalar_one()
        return int(count)
