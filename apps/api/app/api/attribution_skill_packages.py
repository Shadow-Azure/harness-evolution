"""Workspace administration endpoints for attribution Skill ZIP packages."""

from typing import Annotated, Any, cast

from fastapi import (
    APIRouter,
    Depends,
    File,
    Path,
    Request,
    Response,
    Security,
    UploadFile,
    status,
)

from app.api.auth import identity_from
from app.api.deps import require_workspace_role
from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.evolution.attribution_skill_packages import (
    MAX_ARCHIVE_BYTES,
    AttributionSkillPackage,
    AttributionSkillPackageList,
    AttributionSkillPackageService,
    SkillResourceDetail,
)
from app.service.identity.principals import Principal
from app.service.workspaces.service import WorkspaceAccess

router = APIRouter(
    prefix="/api/workspaces/{wid}/attribution-skill-packages",
    tags=["attribution-skill-packages"],
)

WorkspaceId = Annotated[str, Path(min_length=1, max_length=36)]
PackageId = Annotated[str, Path(min_length=1, max_length=64)]
ViewerAccess = Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))]
AdminAccess = Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))]

RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required"},
    403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
    404: {"model": ErrorResponse, "description": "Package or workspace is missing"},
    409: {"model": ErrorResponse, "description": "Skill name already exists"},
    413: {"model": ErrorResponse, "description": "ZIP package exceeds a safety limit"},
    422: {"model": ErrorResponse, "description": "ZIP or SKILL.md is invalid"},
}


def packages_from(request: Request) -> AttributionSkillPackageService:
    """Return the application-scoped package service."""
    return cast(AttributionSkillPackageService, request.app.state.attribution_skill_packages)


@router.get(
    "",
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def list_attribution_skill_packages(
    request: Request,
    wid: WorkspaceId,
    access: ViewerAccess,
) -> AttributionSkillPackageList:
    """List the built-in package and workspace uploads."""
    del access
    return await packages_from(request).list(wid)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def upload_attribution_skill_package(
    request: Request,
    wid: WorkspaceId,
    access: AdminAccess,
    file: Annotated[UploadFile, File(description="Attribution Skill folder ZIP")],
) -> AttributionSkillPackage:
    """Validate and store one custom Skill folder ZIP without activating it."""
    del access
    principal = cast(Principal, request.state.principal)
    user = await identity_from(request).get_user(principal.user_id)
    uploader_name = user.display_name if user is not None else principal.user_id
    archive = await file.read(MAX_ARCHIVE_BYTES + 1)
    await file.close()
    return await packages_from(request).upload(
        workspace_id=wid,
        uploader_id=principal.user_id,
        uploader_name=uploader_name,
        archive_name=file.filename or "attribution-skill.zip",
        archive=archive,
    )


@router.get("/{packageId}", dependencies=[Security(BEARER_AUTH)], responses=RESPONSES)
async def get_package_detail(
    request: Request, wid: WorkspaceId, packageId: PackageId, access: ViewerAccess
) -> SkillResourceDetail:
    """Return the selected package prompt, file paths and target bindings."""
    return await packages_from(request).detail(wid, packageId)


@router.get(
    "/{packageId}/download",
    dependencies=[Security(BEARER_AUTH)],
    response_class=Response,
    responses={
        **RESPONSES,
        200: {
            "description": "Attribution Skill folder ZIP",
            "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
        },
    },
)
async def download_attribution_skill_package(
    request: Request,
    wid: WorkspaceId,
    packageId: PackageId,
    access: ViewerAccess,
) -> Response:
    """Download a regenerated ZIP without exposing server filesystem paths."""
    del access
    filename, payload = await packages_from(request).download(wid, packageId)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete(
    "/{packageId}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def delete_attribution_skill_package(
    request: Request,
    wid: WorkspaceId,
    packageId: PackageId,
    access: AdminAccess,
) -> Response:
    """Remove a custom package that has no target bindings."""
    del access
    await packages_from(request).delete(wid, packageId)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
