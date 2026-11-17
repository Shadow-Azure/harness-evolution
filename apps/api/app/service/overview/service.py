"""Overview assembly: request validation, window resolution, and DTO mapping."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import cast

from app.db.crud.overview import BadCasePageRow, BadCaseTypeFilter, OverviewRepository
from app.errors import AppError, ErrorCode
from app.service.bad_cases.session_status import classify_trace_status
from app.service.overview.schemas import (
    BadCaseListItem,
    BadCaseType,
    OverviewBadCaseListResponse,
    OverviewSummary,
    OverviewTotals,
    OverviewWindow,
    SourceListResponse,
    SourceRow,
    TrendBucket,
    TrendResponse,
)
from app.service.overview.window import (
    Window,
    bucket_label,
    bucket_start,
    bucket_starts,
    resolve_window,
)
from app.utils.time import as_shanghai

MAX_OBJECTS = 50
"""Largest accepted object selection; a broader filter is a 422."""

TYPE_LABELS: dict[str, str] = {
    "self": "自身存在问题",
    "discovery": "发现前置步骤问题",
}
"""Server-side display labels so the list never re-derives them in the browser."""


@dataclass(frozen=True, slots=True)
class OverviewQuery:
    """Validated window and object selection shared by every overview endpoint."""

    date_from: date | None = None
    date_to: date | None = None
    range_days: int | None = None
    grain: str = "day"
    objects: tuple[str, ...] = ()

    def window(self) -> Window:
        """Resolve the inclusive window (or raise a documented 422)."""
        return resolve_window(
            date_from=self.date_from,
            date_to=self.date_to,
            range_days=self.range_days,
            grain=self.grain,
        )


@dataclass(frozen=True, slots=True)
class BadCaseListQuery:
    """Window, object, and type filters plus the page bounds."""

    window: OverviewQuery = field(default_factory=OverviewQuery)
    bad_case_type: BadCaseTypeFilter = "all"
    page: int = 1
    page_size: int = 8


def parse_object_filter(values: Sequence[str] | None) -> tuple[str, ...]:
    """Flatten repeated and comma-separated object filters into one ordered set.

    An empty or all-blank selection means "all objects" and yields ``()``, which
    the repository turns into no predicate. Trimming happens before the dedupe so
    ``[" a ", "a"]`` and ``["a,b"]`` never produce duplicate names.
    """
    if not values:
        return ()
    selected: list[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in raw.split(","):
            name = part.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            selected.append(name)
    if len(selected) > MAX_OBJECTS:
        raise AppError(
            status_code=422,
            code=ErrorCode.OBJECT_FILTER_TOO_LARGE,
            message=f"at most {MAX_OBJECTS} objects can be selected",
            details={"count": len(selected), "max": MAX_OBJECTS},
        )
    return tuple(selected)


def _window_dto(window: Window) -> OverviewWindow:
    """Map the resolved window into its wire contract."""
    return OverviewWindow(date_from=window.start, date_to=window.end)


def _label(bad_case_type: str) -> str:
    """Return the stable Chinese label, degrading to the raw type when unknown."""
    return TYPE_LABELS.get(bad_case_type, bad_case_type)


def _item(row: BadCasePageRow) -> BadCaseListItem:
    """Map one aggregated row to the overview list contract.

    ``triggerAt`` mirrors ``createdAt`` until m9-04 stores the object trigger
    coordinates; exposing the report time keeps the field present for the client
    without inventing a schema column.
    """
    created_at = as_shanghai(row.created_at)
    trace = classify_trace_status(row.sync_state, session_ready=row.session_present)
    return BadCaseListItem(
        bad_case_id=row.bad_case_id,
        session_id=row.bad_case_session_id,
        object_name=row.object_name,
        bad_case_type=cast(BadCaseType, row.bad_case_type),
        bad_case_type_label=_label(row.bad_case_type),
        title=row.title,
        trigger_at=created_at,
        created_at=created_at,
        sync_status=trace.status,
        session_ready=trace.session_ready,
        last_error=trace.last_error,
        retryable=trace.retryable,
        next_retry_at=trace.next_retry_at,
        attribution_count=row.attribution_count,
    )


class OverviewService:
    """Aggregate one workspace's reported cases into the overview contracts."""

    def __init__(self, repository: OverviewRepository) -> None:
        """Bind the service to its read-only repository."""
        self._repository = repository

    async def summary(self, workspace_id: str, query: OverviewQuery) -> OverviewSummary:
        """Return the summary totals, object options, and workspace quota usage."""
        window = query.window()
        counts = await self._repository.counts(
            workspace_id=workspace_id,
            start=window.start,
            end=window.end,
            objects=query.objects,
        )
        quota, used = await self._repository.workspace_usage(workspace_id)
        objects = await self._repository.object_options(
            workspace_id=workspace_id,
            start=window.start,
            end=window.end,
        )
        return OverviewSummary(
            window=_window_dto(window),
            totals=OverviewTotals(
                bad_cases=counts.bad_cases,
                self_cases=counts.self_cases,
                discovery_cases=counts.discovery_cases,
                sessions=counts.sessions,
                sources=counts.sources,
                quota=quota,
                used=used,
            ),
            objects=objects,
        )

    async def trend(self, workspace_id: str, query: OverviewQuery) -> TrendResponse:
        """Return a continuous, zero-filled series and the grain it actually used."""
        window = query.window()
        points = await self._repository.trend_points(
            workspace_id=workspace_id,
            start=window.start,
            end=window.end,
            objects=query.objects,
        )
        starts = bucket_starts(window)
        self_counts = dict.fromkeys(starts, 0)
        discovery_counts = dict.fromkeys(starts, 0)
        for point in points:
            local_day = as_shanghai(point.created_at).date()
            if not window.start <= local_day <= window.end:
                continue
            start = bucket_start(local_day, window.grain)
            if start not in self_counts:
                continue
            if point.bad_case_type == "self":
                self_counts[start] += 1
            elif point.bad_case_type == "discovery":
                discovery_counts[start] += 1
        return TrendResponse(
            window=_window_dto(window),
            grain=window.grain,
            buckets=[
                TrendBucket(
                    bucket=start,
                    label=bucket_label(start, window.grain),
                    self_cases=self_counts[start],
                    discovery_cases=discovery_counts[start],
                    total=self_counts[start] + discovery_counts[start],
                )
                for start in starts
            ],
        )

    async def sources(self, workspace_id: str, query: OverviewQuery) -> SourceListResponse:
        """Return the object distribution for the resolved window."""
        window = query.window()
        records = await self._repository.sources(
            workspace_id=workspace_id,
            start=window.start,
            end=window.end,
            objects=query.objects,
        )
        return SourceListResponse(
            items=[
                SourceRow(
                    object=record.object_name,
                    total=record.total,
                    self_cases=record.self_cases,
                    discovery_cases=record.discovery_cases,
                    sessions=record.sessions,
                )
                for record in records
            ],
        )

    async def list_cases(
        self,
        workspace_id: str,
        query: BadCaseListQuery,
    ) -> OverviewBadCaseListResponse:
        """Return one filtered page ordered by ``createdAt`` descending."""
        window = query.window.window()
        total = await self._repository.count_cases(
            workspace_id=workspace_id,
            start=window.start,
            end=window.end,
            objects=query.window.objects,
            bad_case_type=query.bad_case_type,
        )
        rows = await self._repository.page_cases(
            workspace_id=workspace_id,
            start=window.start,
            end=window.end,
            objects=query.window.objects,
            bad_case_type=query.bad_case_type,
            page=query.page,
            page_size=query.page_size,
        )
        return OverviewBadCaseListResponse(
            items=[_item(row) for row in rows],
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
