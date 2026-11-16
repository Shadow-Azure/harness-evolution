"""Multi-attribution, cache, and run-candidate persistence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import RowMapping

from app.db.base import Database
from app.db.models.domain import bad_case_analysis, probe_reports
from app.db.models.evolution import (
    EvolutionRunCandidateRecord,
    evolution_run_candidates,
    record_from_evolution_run_candidate,
)
from app.utils.time import as_shanghai

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

    def __post_init__(self) -> None:
        """Reject malformed identities and normalize an empty object version."""
        for field_name in ("probe_id", "workspace_id", "bad_case_id", "session_id"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")
        if self.probe_type not in {"skill", "agent"}:
            raise ValueError(f"unknown probe_type: {self.probe_type}")
        if self.conclusion not in {"attributed", "non_target"}:
            raise ValueError(f"unknown conclusion: {self.conclusion}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0, 1]: {self.confidence}")
        if self.object_version == "":
            object.__setattr__(self, "object_version", None)

    @property
    def cache_key(self) -> str:
        """Derive the cache key from the persisted identity fields."""
        return attribution_cache_key(
            self.workspace_id,
            self.bad_case_id,
            self.probe_type,
            self.probe_object,
            self.object_version,
            self.policy_version,
            self.attribution_engine,
        )


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
    created_run_id: str | None
    last_reused_run_id: str | None
    reused_count: int
    analysis_status: str | None
    analysis_result: object | None
    created_at: datetime
    updated_at: datetime


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
        created_run_id=_text(mapping["created_run_id"]),
        last_reused_run_id=_text(mapping["last_reused_run_id"]),
        reused_count=int(mapping["reused_count"]),
        analysis_status=_text(mapping["analysis_status"]),
        analysis_result=mapping["analysis_result"],
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
            "updated_at": write.updated_at,
        }
        if write.created_run_id is not None:
            updates["created_run_id"] = write.created_run_id
        statement = self._probe_upsert_statement(values, updates)
        async with self._database.transaction() as session:
            await session.execute(statement)
            probe_id = str(
                (
                    await session.execute(
                        select(probe_reports.c.probe_id).where(
                            probe_reports.c.cache_key == write.cache_key,
                        ),
                    )
                ).scalar_one(),
            )
        return probe_id

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
        values: dict[str, object] = {
            "bad_case_id": bad_case_id,
            "analysis_status": None,
            "probe_id": probe_id,
            "analysis_result": None,
            "updated_at": now,
        }
        dialect = self._database.dialect
        statement: Any
        if dialect == "sqlite":
            statement = (
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
        elif dialect == "mysql":
            statement = (
                mysql_insert(bad_case_analysis)
                .values(**values)
                .on_duplicate_key_update(updated_at=now)
            )
        else:
            raise ValueError(f"unsupported database dialect for attribution link: {dialect}")
        async with self._database.transaction() as session:
            await session.execute(statement)

    async def reuse(self, probe_id: str, run_id: str, now: datetime) -> int:
        """Record one cache hit, at most once per run.

        Returns:
            The number of updated rows: 0 for an unknown probe or a repeated hit
            from the same run, 1 when the counter advanced.
        """
        statement = (
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
        async with self._database.transaction() as session:
            result = await session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)

    async def list_attributions(
        self,
        case_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[AttributionRecord, ...]:
        """Return one case's attributions in the documented page order."""
        statement = (
            self._attribution_statement()
            .where(bad_case_analysis.c.bad_case_id == case_id)
            .order_by(probe_reports.c.updated_at.desc(), probe_reports.c.probe_id)
            .offset(offset)
            .limit(limit)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return tuple(_row_attribution(row) for row in rows)

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
        statement: Any
        if dialect == "sqlite":
            statement = (
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
        elif dialect == "mysql":
            statement = (
                mysql_insert(evolution_run_candidates)
                .values(
                    **values,
                )
                .on_duplicate_key_update(**updates)
            )
        else:
            raise ValueError(f"unsupported database dialect for candidate upsert: {dialect}")
        async with self._database.transaction() as session:
            await session.execute(statement)

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
