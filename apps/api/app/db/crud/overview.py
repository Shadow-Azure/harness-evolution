"""Read-only SQL aggregations behind the workspace overview endpoints.

Every statement is pinned to one workspace id and, except for the workspace
quota/used pair, to the resolved local window. The external ``bad_cases`` table
is bootstrapped outside migrations, so an installation that has not created it
yet degrades to zero counters instead of failing the overview page; the same
applies to the attribution tables, which only affect ``attributionCount``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal, cast

from sqlalchemy import case, func, inspect, select
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import Database
from app.db.crud.bad_case_sync import BadCaseRootSyncRow, _to_row
from app.db.external_contract import read_only_guard
from app.db.models.domain import (
    bad_case_analysis,
    bad_case_root_sync,
    bad_cases,
    probe_reports,
    session_families,
)
from app.db.models.workspace import workspaces
from app.utils.time import SHANGHAI

BadCaseTypeFilter = Literal["all", "self", "discovery"]

KNOWN_BAD_CASE_TYPES: tuple[str, ...] = ("self", "discovery")
"""Types the overview aggregates; every other stored value is excluded consistently."""


@dataclass(frozen=True, slots=True)
class OverviewCounts:
    """Window-scoped counters for the summary strip."""

    bad_cases: int
    self_cases: int
    discovery_cases: int
    sessions: int
    sources: int


@dataclass(frozen=True, slots=True)
class SourceAggregate:
    """One row of the per-object source distribution."""

    object_name: str
    total: int
    self_cases: int
    discovery_cases: int
    sessions: int


@dataclass(frozen=True, slots=True)
class TrendPoint:
    """One reported case reduced to what bucket filling needs."""

    created_at: datetime
    bad_case_type: str


@dataclass(frozen=True, slots=True)
class BadCasePageRow:
    """One row of the filtered overview list plus its derived trace state."""

    bad_case_id: str
    bad_case_session_id: str
    object_name: str
    bad_case_type: str
    trigger_line: int | None
    title: str
    created_at: datetime
    attribution_count: int
    sync_state: BadCaseRootSyncRow | None
    session_present: bool


def day_start(day: date) -> datetime:
    """Return the Asia/Shanghai midnight that opens one inclusive local day."""
    return datetime.combine(day, time.min, tzinfo=SHANGHAI)


def _count(expression: object) -> int:
    """Coerce a dialect aggregate (int or Decimal) to a plain integer."""
    return int(str(expression))


def _flag(column: ColumnElement[str], value: str) -> ColumnElement[int]:
    """Return a 1/0 flag column so self/discovery counts share one aggregate row."""
    return case((column == value, 1), else_=0)


def _case_conditions(
    *,
    workspace_id: str,
    start: date | None,
    end: date | None,
    objects: tuple[str, ...],
    bad_case_type: BadCaseTypeFilter,
) -> list[ColumnElement[bool]]:
    """Build the predicate set shared by listing, counting, and aggregation.

    A missing ``start``/``end`` means the caller asked for every reported case
    (the list's empty date filter), so no date predicate is added. Aggregation
    reads always pass both boundaries.
    """
    conditions: list[ColumnElement[bool]] = [
        bad_cases.c.workspace_id == workspace_id,
        # Legacy catalog sync only enforces the column length, so a row can carry
        # a type outside the report contract. Excluding it here keeps
        # badCases == self + discovery and the trend total on every read path.
        bad_cases.c.bad_case_type.in_(KNOWN_BAD_CASE_TYPES),
    ]
    if start is not None and end is not None:
        conditions.extend(
            [
                bad_cases.c.created_at >= day_start(start),
                bad_cases.c.created_at < day_start(end + timedelta(days=1)),
            ]
        )
    if objects:
        conditions.append(bad_cases.c.object_name.in_(objects))
    if bad_case_type != "all":
        conditions.append(bad_cases.c.bad_case_type == bad_case_type)
    return conditions


class OverviewRepository:
    """Run the SQL-backed overview read paths for one workspace at a time."""

    def __init__(self, database: Database) -> None:
        """Bind this repository to the application database."""
        self._database = database
        self._presence: dict[str, bool] = {}

    async def _table_present(self, name: str) -> bool:
        """Return whether an externally bootstrapped table exists, caching the probe."""
        if name not in self._presence:
            async with self._database.engine.connect() as connection:
                self._presence[name] = bool(
                    await connection.run_sync(
                        lambda sync_connection: inspect(sync_connection).has_table(name),
                    ),
                )
        return self._presence[name]

    async def _cases_available(self) -> bool:
        """Return whether the external bad-case table can be queried."""
        return await self._table_present(bad_cases.name)

    @read_only_guard("bad_cases", strict=False)
    async def counts(
        self,
        *,
        workspace_id: str,
        start: date,
        end: date,
        objects: tuple[str, ...],
        bad_case_type: BadCaseTypeFilter = "all",
    ) -> OverviewCounts:
        """Aggregate the summary totals in one grouped-free aggregate row."""
        if not await self._cases_available():
            return OverviewCounts(
                bad_cases=0,
                self_cases=0,
                discovery_cases=0,
                sessions=0,
                sources=0,
            )
        statement = (
            select(
                func.count().label("bad_cases"),
                func.coalesce(func.sum(_flag(bad_cases.c.bad_case_type, "self")), 0).label(
                    "self_cases",
                ),
                func.coalesce(func.sum(_flag(bad_cases.c.bad_case_type, "discovery")), 0).label(
                    "discovery_cases",
                ),
                func.count(func.distinct(bad_cases.c.bad_case_session_id)).label("sessions"),
                func.count(func.distinct(bad_cases.c.object_name)).label("sources"),
            )
            .select_from(bad_cases)
            .where(
                *_case_conditions(
                    workspace_id=workspace_id,
                    start=start,
                    end=end,
                    objects=objects,
                    bad_case_type=bad_case_type,
                )
            )
        )
        async with self._database.session() as session:
            row = (await session.execute(statement)).mappings().one()
        return OverviewCounts(
            bad_cases=int(row["bad_cases"]),
            self_cases=_count(row["self_cases"]),
            discovery_cases=_count(row["discovery_cases"]),
            sessions=int(row["sessions"]),
            sources=int(row["sources"]),
        )

    @read_only_guard("bad_cases", strict=False)
    async def workspace_usage(self, workspace_id: str) -> tuple[int, int]:
        """Return the workspace quota and its unwindowed bad-case usage."""
        cases_available = await self._cases_available()
        async with self._database.session() as session:
            quota = (
                await session.execute(
                    select(workspaces.c.quota).where(workspaces.c.id == workspace_id),
                )
            ).scalar_one_or_none()
            if quota is None:
                return 0, 0
            used = 0
            if cases_available:
                used = int(
                    (
                        await session.execute(
                            select(func.count())
                            .select_from(bad_cases)
                            .where(bad_cases.c.workspace_id == workspace_id),
                        )
                    ).scalar_one(),
                )
        return int(quota), used

    @read_only_guard("bad_cases", strict=False)
    async def object_options(
        self,
        *,
        workspace_id: str,
        start: date,
        end: date,
    ) -> list[str]:
        """List the distinct object names in the window, ignoring the object filter."""
        if not await self._cases_available():
            return []
        statement = (
            select(bad_cases.c.object_name)
            .where(
                *_case_conditions(
                    workspace_id=workspace_id,
                    start=start,
                    end=end,
                    objects=(),
                    bad_case_type="all",
                )
            )
            .group_by(bad_cases.c.object_name)
            .order_by(func.lower(bad_cases.c.object_name), bad_cases.c.object_name)
        )
        async with self._database.session() as session:
            names: Sequence[object] = (await session.execute(statement)).scalars().all()
        return [str(name) for name in names]

    @read_only_guard("bad_cases", strict=False)
    async def trend_points(
        self,
        *,
        workspace_id: str,
        start: date,
        end: date,
        objects: tuple[str, ...],
    ) -> list[TrendPoint]:
        """Read the window's report timestamps and types for Python bucketing."""
        if not await self._cases_available():
            return []
        statement = (
            select(bad_cases.c.created_at, bad_cases.c.bad_case_type)
            .where(
                *_case_conditions(
                    workspace_id=workspace_id,
                    start=start,
                    end=end,
                    objects=objects,
                    bad_case_type="all",
                )
            )
            .order_by(bad_cases.c.created_at, bad_cases.c.bad_case_id)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).all()
        points: list[TrendPoint] = []
        for created_at, bad_case_type in rows:
            points.append(
                TrendPoint(
                    created_at=cast(datetime, created_at),
                    bad_case_type=str(bad_case_type),
                ),
            )
        return points

    @read_only_guard("bad_cases", strict=False)
    async def sources(
        self,
        *,
        workspace_id: str,
        start: date,
        end: date,
        objects: tuple[str, ...],
    ) -> list[SourceAggregate]:
        """Aggregate per-object totals, split by type, sorted by total then name."""
        if not await self._cases_available():
            return []
        total = func.count()
        statement = (
            select(
                bad_cases.c.object_name,
                total.label("total"),
                func.coalesce(func.sum(_flag(bad_cases.c.bad_case_type, "self")), 0).label(
                    "self_cases",
                ),
                func.coalesce(func.sum(_flag(bad_cases.c.bad_case_type, "discovery")), 0).label(
                    "discovery_cases",
                ),
                func.count(func.distinct(bad_cases.c.bad_case_session_id)).label("sessions"),
            )
            .where(
                *_case_conditions(
                    workspace_id=workspace_id,
                    start=start,
                    end=end,
                    objects=objects,
                    bad_case_type="all",
                )
            )
            .group_by(bad_cases.c.object_name)
            .order_by(total.desc(), bad_cases.c.object_name)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
        return [
            SourceAggregate(
                object_name=str(row["object_name"]),
                total=int(row["total"]),
                self_cases=_count(row["self_cases"]),
                discovery_cases=_count(row["discovery_cases"]),
                sessions=int(row["sessions"]),
            )
            for row in rows
        ]

    @read_only_guard("bad_cases", strict=False)
    async def count_cases(
        self,
        *,
        workspace_id: str,
        start: date | None,
        end: date | None,
        objects: tuple[str, ...],
        bad_case_type: BadCaseTypeFilter,
    ) -> int:
        """Count every case matching the filters without applying the page bounds."""
        if not await self._cases_available():
            return 0
        statement = (
            select(func.count())
            .select_from(bad_cases)
            .where(
                *_case_conditions(
                    workspace_id=workspace_id,
                    start=start,
                    end=end,
                    objects=objects,
                    bad_case_type=bad_case_type,
                )
            )
        )
        async with self._database.session() as session:
            return int((await session.execute(statement)).scalar_one())

    @read_only_guard("bad_cases", strict=False)
    async def page_cases(
        self,
        *,
        workspace_id: str,
        start: date | None,
        end: date | None,
        objects: tuple[str, ...],
        bad_case_type: BadCaseTypeFilter,
        page: int,
        page_size: int,
    ) -> list[BadCasePageRow]:
        """Return one page ordered by ``created_at DESC, bad_case_id ASC``."""
        if not await self._cases_available():
            return []
        statement = (
            select(
                bad_cases.c.bad_case_id,
                bad_cases.c.bad_case_session_id,
                bad_cases.c.object_name,
                bad_cases.c.bad_case_type,
                bad_cases.c.trigger_line,
                bad_cases.c.title,
                bad_cases.c.created_at,
            )
            .where(
                *_case_conditions(
                    workspace_id=workspace_id,
                    start=start,
                    end=end,
                    objects=objects,
                    bad_case_type=bad_case_type,
                )
            )
            .order_by(bad_cases.c.created_at.desc(), bad_cases.c.bad_case_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        async with self._database.session() as session:
            rows = (await session.execute(statement)).mappings().all()
            roots = tuple(dict.fromkeys(str(row["bad_case_session_id"]) for row in rows))
            sync_states: dict[str, BadCaseRootSyncRow] = {}
            present_roots: set[str] = set()
            if roots:
                state_rows = (
                    (
                        await session.execute(
                            select(bad_case_root_sync).where(
                                bad_case_root_sync.c.root_session_id.in_(roots),
                            ),
                        )
                    )
                    .mappings()
                    .all()
                )
                sync_states = {
                    str(state["root_session_id"]): _to_row(state) for state in state_rows
                }
                present_rows: Sequence[object] = (
                    (
                        await session.execute(
                            select(session_families.c.id).where(
                                session_families.c.id.in_(roots),
                            ),
                        )
                    )
                    .scalars()
                    .all()
                )
                present_roots = {str(root) for root in present_rows}
        case_ids = [str(row["bad_case_id"]) for row in rows]
        counts = await self._attribution_counts(case_ids)
        return [
            BadCasePageRow(
                bad_case_id=str(row["bad_case_id"]),
                bad_case_session_id=str(row["bad_case_session_id"]),
                object_name=str(row["object_name"]),
                bad_case_type=str(row["bad_case_type"]),
                trigger_line=(
                    int(row["trigger_line"]) if row["trigger_line"] is not None else None
                ),
                title=str(row["title"]),
                created_at=row["created_at"],
                attribution_count=counts.get(str(row["bad_case_id"]), 0),
                sync_state=sync_states.get(str(row["bad_case_session_id"])),
                session_present=str(row["bad_case_session_id"]) in present_roots,
            )
            for row in rows
        ]

    async def _attribution_counts(self, case_ids: list[str]) -> dict[str, int]:
        """Count distinct attribution object/version triples for the current page."""
        if not case_ids:
            return {}
        analysis_ready = await self._table_present(bad_case_analysis.name)
        reports_ready = await self._table_present(probe_reports.name)
        if not analysis_ready or not reports_ready:
            return {}
        triples = (
            select(
                bad_case_analysis.c.bad_case_id,
                probe_reports.c.probe_type,
                probe_reports.c.probe_object,
                probe_reports.c.object_version,
            )
            .select_from(bad_case_analysis)
            .join(probe_reports, probe_reports.c.probe_id == bad_case_analysis.c.probe_id)
            .where(bad_case_analysis.c.bad_case_id.in_(case_ids))
            .distinct()
            .subquery()
        )
        statement = select(
            triples.c.bad_case_id,
            func.count().label("attributions"),
        ).group_by(triples.c.bad_case_id)
        async with self._database.session() as session:
            attributions = (await session.execute(statement)).all()
        return {str(case_id): int(str(count)) for case_id, count in attributions}
