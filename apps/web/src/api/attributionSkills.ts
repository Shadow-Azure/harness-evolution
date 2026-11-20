import type {
  AttributionSkillBindingWrite,
  AttributionSkillList,
  EffectiveAttributionSkill,
} from "@harness/contracts";

import { request } from "./http";

function evolutionPath(workspaceId: string, suffix: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/evolution${suffix}`;
}

/**
 * List every published Attribution Skill revision visible to one workspace.
 * @param workspaceId Route workspace identifier.
 * @returns Platform and workspace Skill revisions.
 */
export function listAttributionSkills(
  workspaceId: string,
): Promise<AttributionSkillList> {
  return request<AttributionSkillList>(
    evolutionPath(workspaceId, "/attribution-skills"),
  );
}

/**
 * Resolve the effective Attribution Skill for one configured target.
 * @param workspaceId Route workspace identifier.
 * @param targetId Stable evolution target identifier.
 * @returns Effective immutable revision and binding source.
 */
export function getTargetAttributionSkill(
  workspaceId: string,
  targetId: string,
): Promise<EffectiveAttributionSkill> {
  return request<EffectiveAttributionSkill>(
    evolutionPath(
      workspaceId,
      `/targets/${encodeURIComponent(targetId)}/attribution-skill`,
    ),
  );
}

/**
 * Bind one published Skill revision as a target override.
 * @param workspaceId Route workspace identifier.
 * @param targetId Stable evolution target identifier.
 * @param body Selected immutable revision.
 * @returns Newly effective target binding.
 */
export function bindTargetAttributionSkill(
  workspaceId: string,
  targetId: string,
  body: AttributionSkillBindingWrite,
): Promise<EffectiveAttributionSkill> {
  return request<EffectiveAttributionSkill>(
    evolutionPath(
      workspaceId,
      `/targets/${encodeURIComponent(targetId)}/attribution-skill`,
    ),
    { method: "PUT", body: JSON.stringify(body) },
  );
}

/**
 * Remove the target override and restore workspace/platform fallback.
 * @param workspaceId Route workspace identifier.
 * @param targetId Stable evolution target identifier.
 * @returns No value.
 */
export function unbindTargetAttributionSkill(
  workspaceId: string,
  targetId: string,
): Promise<void> {
  return request<void>(
    evolutionPath(
      workspaceId,
      `/targets/${encodeURIComponent(targetId)}/attribution-skill`,
    ),
    { method: "DELETE" },
  );
}
