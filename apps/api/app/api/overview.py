"""Read-only HTTP adapters for the workspace bad-case overview."""

from collections.abc import Callable, Coroutine
from datetime import date
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import Response

from app.api.deps import require_workspace_role
from app.api.security import BEARER_AUTH
from app.db.crud.overview import BadCaseTypeFilter
from app.errors import AppError, ErrorCode, ErrorResponse
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
from app.service.overview.target_schemas import (
    TARGET_STATES,
    TargetCaseListResponse,
    TargetDetailResponse,
    TargetOverviewListResponse,
    TargetTrendResponse,
)
from app.service.overview.targets import (
    DEFAULT_CASE_PAGE_SIZE,
    DEFAULT_TARGET_PAGE_SIZE,
    DEFAULT_VERSION_LIMIT,
    TargetOverviewQuery,
    TargetOverviewService,
    parse_state_filter,
    parse_target_filter,
    parse_version_filter,
    parse_version_limit,
)
from app.service.overview.window import GRAINS, RANGE_CHOICES, Grain
from app.service.workspaces.service import WorkspaceAccess


class OverviewRoute(APIRoute):
    """Map an invalid trend grain back to the documented ``GRAIN_INVALID`` code.

    ``grain`` is a ``Literal`` so OpenAPI exposes the allowed values and generated
    clients get the union. FastAPI validates it before the handler, which would
    otherwise turn ``?grain=hour`` into the generic ``VALIDATION_INVALID``; the
    route wrapper restores the dedicated error the contract promises.
    """

    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Wrap the generated handler with the overview validation mapping."""
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                grain_error = next(
                    (
                        error
                        for error in exc.errors()
                        if tuple(error.get("loc", ()))[-1:] == ("grain",)
                    ),
                    None,
                )
                if grain_error is None:
                    raise
                raise AppError(
                    status_code=422,
                    code=ErrorCode.GRAIN_INVALID,
                    message="grain must be one of day, week, month",
                    details={
                        "grain": grain_error.get("input"),
                        "allowed": list(GRAINS),
                    },
                ) from exc

        return handle


router = APIRouter(
    prefix="/api/workspaces/{wid}",
    tags=["overview"],
    route_class=OverviewRoute,
)

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
            "Quick range in days; only 7, 30, and 90 are accepted when it derives a "
            "boundary, and it is ignored when both from and to are supplied. Defaults "
            "to 90 when neither from nor to is supplied."
        ),
        json_schema_extra={"enum": list(RANGE_CHOICES)},
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
    Grain,
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
AllTimeQuery = Annotated[
    bool,
    Query(
        alias="allTime",
        description=(
            "Return every reported case regardless of date; the list's empty date "
            "filter sends this, and any from/to/range is then ignored."
        ),
    ),
]
PageNumber = Annotated[int, Query(alias="page", ge=1, description="1-based page number.")]
PageSize = Annotated[
    int,
    Query(alias="pageSize", ge=1, le=50, description="Page size; defaults to 8."),
]
TargetId = Annotated[str, Path(alias="targetId", min_length=1, max_length=36)]
TargetsFilter = Annotated[
    list[str] | None,
    Query(
        alias="targets",
        description=(
            "Evolution target ids to include. Repeat the parameter or pass a "
            "comma-separated value; empty means every enabled target."
        ),
    ),
]
StatesFilter = Annotated[
    list[str] | None,
    Query(
        alias="states",
        description=(
            "Attribution states to include: attributed, nonTarget, or unanalyzed. "
            "Repeat the parameter or pass a comma-separated value; empty means all."
        ),
        json_schema_extra={"enum": list(TARGET_STATES)},
    ),
]
VersionsFilter = Annotated[
    list[str] | None,
    Query(
        alias="versions",
        description=(
            "Target versions for one detail card. Repeat the parameter or pass a "
            "comma-separated value; empty selects the highest versionLimit versions."
        ),
    ),
]
VersionLimit = Annotated[
    int,
    Query(
        alias="versionLimit",
        ge=0,
        le=20,
        description=("Version count when versions is empty: 5, 10, 20, or 0 for all."),
        json_schema_extra={"enum": [0, 5, 10, 20]},
    ),
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


def target_overview_from(request: Request) -> TargetOverviewService:
    """Return the application-scoped evolution-target overview service."""
    return cast(TargetOverviewService, request.app.state.target_overview)


def _target_query(
    *,
    date_from: date | None,
    date_to: date | None,
    range_days: int | None,
    grain: str = "day",
    targets: list[str] | None = None,
    objects: list[str] | None = None,
    states: list[str] | None = None,
    versions: list[str] | None = None,
    version_limit: int = DEFAULT_VERSION_LIMIT,
    page: int = 1,
    page_size: int = DEFAULT_TARGET_PAGE_SIZE,
) -> TargetOverviewQuery:
    """Assemble one validated target-overview query from raw query parameters."""
    window = OverviewQuery(
        date_from=date_from,
        date_to=date_to,
        range_days=range_days,
        grain=grain,
    ).window()
    return TargetOverviewQuery(
        window=window,
        targets=parse_target_filter(targets),
        objects=parse_object_filter(objects),
        states=parse_state_filter(states),
        versions=parse_version_filter(versions),
        version_limit=parse_version_limit(version_limit),
        page=page,
        page_size=page_size,
    )


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
    all_time: AllTimeQuery = False,
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
            all_time=all_time,
        ),
    )


@router.get(
    "/overview/targets",
    dependencies=[Security(BEARER_AUTH)],
    responses=WORKSPACE_READ_RESPONSES,
)
async def get_overview_targets(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    date_from: WindowFrom = None,
    date_to: WindowTo = None,
    range_days: RangeDays = None,
    page: PageNumber = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", ge=1, le=50, description="Page size; defaults to 5."),
    ] = DEFAULT_TARGET_PAGE_SIZE,
) -> TargetOverviewListResponse:
    """Return target summary totals and one evolvable-sorted page."""
    return await target_overview_from(request).list_targets(
        access.workspace_id,
        _target_query(
            date_from=date_from,
            date_to=date_to,
            range_days=range_days,
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/overview/targets/trend",
    dependencies=[Security(BEARER_AUTH)],
    responses=WORKSPACE_READ_RESPONSES,
)
async def get_overview_targets_trend(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    date_from: WindowFrom = None,
    date_to: WindowTo = None,
    range_days: RangeDays = None,
    targets: TargetsFilter = None,
    states: StatesFilter = None,
    grain: TrendGrainQuery = "day",
) -> TargetTrendResponse:
    """Return the selected targets' three-state trend, zero-filled per bucket."""
    return await target_overview_from(request).trend(
        access.workspace_id,
        _target_query(
            date_from=date_from,
            date_to=date_to,
            range_days=range_days,
            grain=grain,
            targets=targets,
            states=states,
        ),
    )


@router.get(
    "/overview/targets/cases",
    dependencies=[Security(BEARER_AUTH)],
    responses=WORKSPACE_READ_RESPONSES,
)
async def get_overview_target_cases(
    wid: WorkspaceId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    date_from: WindowFrom = None,
    date_to: WindowTo = None,
    range_days: RangeDays = None,
    targets: TargetsFilter = None,
    objects: ObjectFilter = None,
    states: StatesFilter = None,
    page: PageNumber = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", ge=1, le=50, description="Page size; defaults to 8."),
    ] = DEFAULT_CASE_PAGE_SIZE,
) -> TargetCaseListResponse:
    """Return one filtered page of potential cases under their target versions."""
    return await target_overview_from(request).cases(
        access.workspace_id,
        _target_query(
            date_from=date_from,
            date_to=date_to,
            range_days=range_days,
            targets=targets,
            objects=objects,
            states=states,
            page=page,
            page_size=page_size,
        ),
    )


@router.get(
    "/overview/targets/{targetId}/detail",
    dependencies=[Security(BEARER_AUTH)],
    responses={
        **WORKSPACE_READ_RESPONSES,
        404: {"model": ErrorResponse, "description": "Workspace or target does not exist"},
    },
)
async def get_overview_target_detail(
    wid: WorkspaceId,
    target_id: TargetId,
    request: Request,
    access: Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))],
    date_from: WindowFrom = None,
    date_to: WindowTo = None,
    range_days: RangeDays = None,
    versions: VersionsFilter = None,
    version_limit: VersionLimit = 5,
) -> TargetDetailResponse:
    """Return one target's independent version and source analysis."""
    return await target_overview_from(request).detail(
        access.workspace_id,
        target_id,
        _target_query(
            date_from=date_from,
            date_to=date_to,
            range_days=range_days,
            versions=versions,
            version_limit=version_limit,
        ),
    )
