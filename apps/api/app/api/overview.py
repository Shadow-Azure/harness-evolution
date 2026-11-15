"""Read-only HTTP adapters for the workspace bad-case overview."""

from datetime import date
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Security

from app.api.deps import require_workspace_role
from app.api.security import BEARER_AUTH
from app.db.crud.overview import BadCaseTypeFilter
from app.errors import ErrorResponse
from app.service.overview.schemas import (
    OverviewBadCaseListResponse,
    OverviewSummary,
    SourceListResponse,
    TrendResponse,
)
from app.service.overview.service import (
    BadCaseListQuery,
    OverviewQuery,
    OverviewService,
    parse_object_filter,
)
from app.service.workspaces.service import WorkspaceAccess

router = APIRouter(prefix="/api/workspaces/{wid}", tags=["overview"])

WorkspaceId = Annotated[str, Path(min_length=1, max_length=36)]
WindowFrom = Annotated[
    date | None,
    Query(alias="from", description="Inclusive Asia/Shanghai start date (YYYY-MM-DD)."),
]
WindowTo = Annotated[
    date | None,
    Query(alias="to", description="Inclusive Asia/Shanghai end date (YYYY-MM-DD)."),
]
RangeDays = Annotated[
    int | None,
    Query(
        alias="range",
        description=(
            "Quick range in days; only 7, 30, and 90 are accepted. Defaults to 90 "
            "when neither from nor to is supplied."
        ),
    ),
]
ObjectFilter = Annotated[
    list[str] | None,
    Query(
        alias="objects",
        description=(
            "Object names to include. Repeat the parameter or pass a comma-separated "
            "value; empty means every object, and at most 50 distinct names are allowed."
        ),
    ),
]
TrendGrainQuery = Annotated[
    str,
    Query(
        alias="grain",
        description=(
            "Requested trend grain: day, week, or month. A day request longer than 92 "
            "inclusive days is served as week and the response states the effective grain."
        ),
    ),
]
BadCaseTypeQuery = Annotated[
    BadCaseTypeFilter,
    Query(alias="badCaseType", description="Restrict the list to one bad-case type."),
]
PageNumber = Annotated[int, Query(alias="page", ge=1, description="1-based page number.")]
PageSize = Annotated[
    int,
    Query(alias="pageSize", ge=1, le=50, description="Page size; defaults to 8."),
]

WORKSPACE_READ_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required"},
    403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
    404: {"model": ErrorResponse, "description": "Workspace does not exist"},
    422: {"model": ErrorResponse, "description": "Request validation failed"},
}


def overview_from(request: Request) -> OverviewService:
    """Return the application-scoped overview service."""
    return cast(OverviewService, request.app.state.overview)


def _query(
    *,
    date_from: date | None,
    date_to: date | None,
    range_days: int | None,
    grain: str = "day",
    objects: list[str] | None = None,
) -> OverviewQuery:
    """Assemble one validated overview query from raw query parameters."""
    return OverviewQuery(
        date_from=date_from,
        date_to=date_to,
        range_days=range_days,
        grain=grain,
        objects=parse_object_filter(objects),
    )


@router.get(
    "/overview/summary",
    dependencies=[Security(BEARER_AUTH)],
    responses=WORKSPACE_READ_RESPONSES,
)
async def get_overview_summary(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    date_from: WindowFrom = None,
    date_to: WindowTo = None,
    range_days: RangeDays = None,
    objects: ObjectFilter = None,
) -> OverviewSummary:
    """Return this workspace's overview totals, object options, and quota usage."""
    return await overview_from(request).summary(
        access.workspace_id,
        _query(
            date_from=date_from,
            date_to=date_to,
            range_days=range_days,
            objects=objects,
        ),
    )


@router.get(
    "/overview/trend",
    dependencies=[Security(BEARER_AUTH)],
    responses=WORKSPACE_READ_RESPONSES,
)
async def get_overview_trend(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    date_from: WindowFrom = None,
    date_to: WindowTo = None,
    range_days: RangeDays = None,
    grain: TrendGrainQuery = "day",
    objects: ObjectFilter = None,
) -> TrendResponse:
    """Return the continuous self/discovery trend and its effective grain."""
    return await overview_from(request).trend(
        access.workspace_id,
        _query(
            date_from=date_from,
            date_to=date_to,
            range_days=range_days,
            grain=grain,
            objects=objects,
        ),
    )


@router.get(
    "/overview/sources",
    dependencies=[Security(BEARER_AUTH)],
    responses=WORKSPACE_READ_RESPONSES,
)
async def get_overview_sources(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    date_from: WindowFrom = None,
    date_to: WindowTo = None,
    range_days: RangeDays = None,
    objects: ObjectFilter = None,
) -> SourceListResponse:
    """Return the per-object distribution, sorted by total then object name."""
    return await overview_from(request).sources(
        access.workspace_id,
        _query(
            date_from=date_from,
            date_to=date_to,
            range_days=range_days,
            objects=objects,
        ),
    )


@router.get(
    "/bad-cases",
    dependencies=[Security(BEARER_AUTH)],
    responses=WORKSPACE_READ_RESPONSES,
)
async def list_workspace_bad_cases(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    date_from: WindowFrom = None,
    date_to: WindowTo = None,
    range_days: RangeDays = None,
    objects: ObjectFilter = None,
    bad_case_type: BadCaseTypeQuery = "all",
    page: PageNumber = 1,
    page_size: PageSize = 8,
) -> OverviewBadCaseListResponse:
    """Return one filtered page of this workspace's reported cases."""
    return await overview_from(request).list_cases(
        access.workspace_id,
        BadCaseListQuery(
            window=_query(
                date_from=date_from,
                date_to=date_to,
                range_days=range_days,
                objects=objects,
            ),
            bad_case_type=bad_case_type,
            page=page,
            page_size=page_size,
        ),
    )
