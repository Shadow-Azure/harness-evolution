"""Workspace-scoped attribution Skill registry and binding endpoints."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Path, Request, Response, Security, status

from app.api.deps import require_workspace_role
from app.api.security import BEARER_AUTH
from app.errors import ErrorResponse
from app.service.evolution.attribution_skills import (
    AttributionQualityDecisionWrite,
    AttributionQualityEvaluation,
    AttributionQualityHistory,
    AttributionRollbackWrite,
    AttributionSkillBindingWrite,
    AttributionSkillCreate,
    AttributionSkillList,
    AttributionSkillRevision,
    AttributionSkillRevisionWrite,
    AttributionSkillService,
    AttributionSkillStateWrite,
    EffectiveAttributionSkill,
)
from app.service.evolution.local_attribution import LocalAttribution
from app.service.workspaces.service import WorkspaceAccess

router = APIRouter(
    prefix="/api/workspaces/{wid}/evolution",
    tags=["attribution-skills"],
)

WorkspaceId = Annotated[str, Path(min_length=1, max_length=36)]
SkillId = Annotated[str, Path(min_length=1, max_length=36)]
RevisionId = Annotated[str, Path(min_length=1, max_length=36)]
TargetId = Annotated[str, Path(min_length=1, max_length=36)]
ViewerAccess = Annotated[WorkspaceAccess, Depends(require_workspace_role("viewer"))]
AdminAccess = Annotated[WorkspaceAccess, Depends(require_workspace_role("space_admin"))]

RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication is required"},
    403: {"model": ErrorResponse, "description": "Workspace role is insufficient"},
    404: {"model": ErrorResponse, "description": "Skill, target, or workspace is missing"},
    409: {"model": ErrorResponse, "description": "Skill identity or revision conflicts"},
    422: {"model": ErrorResponse, "description": "Skill contract is invalid"},
}


def skills_from(request: Request) -> AttributionSkillService:
    """Return the application-scoped attribution Skill service."""
    return cast(AttributionSkillService, request.app.state.attribution_skills)


@router.get(
    "/attribution-skills",
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def list_attribution_skills(
    request: Request,
    wid: WorkspaceId,
    access: ViewerAccess,
) -> AttributionSkillList:
    """List platform and workspace Skill revisions visible in this workspace."""
    del access
    runtime: LocalAttribution | None = request.app.state.local_attribution
    return await runtime.choices(wid) if runtime else await skills_from(request).list(wid)


@router.post(
    "/attribution-skills",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def create_attribution_skill(
    request: Request,
    wid: WorkspaceId,
    body: AttributionSkillCreate,
    access: AdminAccess,
) -> AttributionSkillRevision:
    """Create a workspace Skill and publish revision one."""
    del access
    return await skills_from(request).create(wid, body)


@router.post(
    "/attribution-skills/{skillId}/revisions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def publish_attribution_skill_revision(
    request: Request,
    wid: WorkspaceId,
    skillId: SkillId,
    body: AttributionSkillRevisionWrite,
    access: AdminAccess,
) -> AttributionSkillRevision:
    """Append a published immutable revision to a workspace Skill."""
    del access
    return await skills_from(request).publish(wid, skillId, body)


@router.patch(
    "/attribution-skills/{skillId}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def set_attribution_skill_state(
    request: Request,
    wid: WorkspaceId,
    skillId: SkillId,
    body: AttributionSkillStateWrite,
    access: AdminAccess,
) -> Response:
    """Enable or disable a workspace Skill for future resolution."""
    del access
    await skills_from(request).set_enabled(wid, skillId, body.enabled)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/attribution-skills/revisions/{revisionId}/shadow-evaluations",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def evaluate_attribution_skill_revision(
    request: Request,
    wid: WorkspaceId,
    revisionId: RevisionId,
    access: AdminAccess,
) -> AttributionQualityEvaluation:
    """Evaluate a revision against sanitized Golden Cases without production writes."""
    del access
    return await skills_from(request).evaluate_revision(
        wid,
        revisionId,
        request.state.principal.user_id,
    )


@router.post(
    "/attribution-skills/revisions/{revisionId}/quality-decisions",
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def decide_attribution_skill_quality(
    request: Request,
    wid: WorkspaceId,
    revisionId: RevisionId,
    body: AttributionQualityDecisionWrite,
    access: AdminAccess,
) -> AttributionSkillRevision:
    """Accept or reject one revision using an exact persisted evaluation."""
    del access
    return await skills_from(request).decide_quality(
        wid,
        revisionId,
        request.state.principal.user_id,
        body,
    )


@router.get(
    "/attribution-skills/revisions/{revisionId}/quality-events",
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def list_attribution_skill_quality_events(
    request: Request,
    wid: WorkspaceId,
    revisionId: RevisionId,
    access: ViewerAccess,
) -> AttributionQualityHistory:
    """Return the immutable evaluation and human-decision audit trail."""
    del access
    return await skills_from(request).quality_history(wid, revisionId)


@router.put(
    "/attribution-skill-bindings/default",
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def bind_workspace_default_skill(
    request: Request,
    wid: WorkspaceId,
    body: AttributionSkillBindingWrite,
    access: AdminAccess,
) -> EffectiveAttributionSkill:
    """Set the workspace fallback revision."""
    del access
    return await skills_from(request).bind(wid, body.skill_revision_id, target_id=None)


@router.delete(
    "/attribution-skill-bindings/default",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def unbind_workspace_default_skill(
    request: Request,
    wid: WorkspaceId,
    access: AdminAccess,
) -> Response:
    """Remove the workspace fallback and restore the platform default."""
    del access
    await skills_from(request).unbind(wid, target_id=None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/attribution-skill-bindings/default/rollback",
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def rollback_workspace_default_skill(
    request: Request,
    wid: WorkspaceId,
    body: AttributionRollbackWrite,
    access: AdminAccess,
) -> EffectiveAttributionSkill:
    """Restore the prior eligible revision or the protected platform rule."""
    del access
    return await skills_from(request).rollback_default(
        wid,
        request.state.principal.user_id,
        body,
    )


@router.get(
    "/targets/{targetId}/attribution-skill",
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def resolve_target_attribution_skill(
    request: Request,
    wid: WorkspaceId,
    targetId: TargetId,
    access: ViewerAccess,
) -> EffectiveAttributionSkill:
    """Resolve the immutable revision currently effective for one target."""
    del access
    runtime: LocalAttribution | None = request.app.state.local_attribution
    return (
        await runtime.effective(wid, targetId)
        if runtime
        else await skills_from(request).resolve(wid, targetId)
    )


@router.put(
    "/targets/{targetId}/attribution-skill",
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def bind_target_attribution_skill(
    request: Request,
    wid: WorkspaceId,
    targetId: TargetId,
    body: AttributionSkillBindingWrite,
    access: AdminAccess,
) -> EffectiveAttributionSkill:
    """Set a target-level Skill override."""
    del access
    runtime: LocalAttribution | None = request.app.state.local_attribution
    if runtime:
        return await runtime.bind(wid, targetId, body.skill_revision_id)
    return await skills_from(request).bind(
        wid,
        body.skill_revision_id,
        target_id=targetId,
    )


@router.delete(
    "/targets/{targetId}/attribution-skill",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(BEARER_AUTH)],
    responses=RESPONSES,
)
async def unbind_target_attribution_skill(
    request: Request,
    wid: WorkspaceId,
    targetId: TargetId,
    access: AdminAccess,
) -> Response:
    """Remove the target override and restore workspace/platform fallback."""
    del access
    await skills_from(request).unbind(wid, target_id=targetId)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
