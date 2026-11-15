import type {
  EvolutionTarget,
  EvolutionTargetList,
  EvolutionTargetVersions,
  EvolutionTargetWrite,
} from "@harness/contracts";

import { request } from "./http";

function workspaceTargetsPath(workspaceId: string, suffix = ""): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/evolution/targets${suffix}`;
}

/**
 * Read every evolution target configuration of one workspace, including disabled rows.
 * @param workspaceId Route workspace identifier.
 * @returns Target configuration collection.
 */
export function listEvolutionTargets(
  workspaceId: string,
): Promise<EvolutionTargetList> {
  return request<EvolutionTargetList>(workspaceTargetsPath(workspaceId));
}

/**
 * Create one evolution target owned by the route workspace.
 * @param workspaceId Route workspace identifier.
 * @param body Mutable target configuration.
 * @returns Persisted target.
 */
export function createEvolutionTarget(
  workspaceId: string,
  body: EvolutionTargetWrite,
): Promise<EvolutionTarget> {
  return request<EvolutionTarget>(workspaceTargetsPath(workspaceId), {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Update one evolution target owned by the route workspace.
 * @param workspaceId Route workspace identifier.
 * @param id Stable target identifier.
 * @param body Mutable target configuration.
 * @returns Updated target.
 */
export function updateEvolutionTarget(
  workspaceId: string,
  id: string,
  body: EvolutionTargetWrite,
): Promise<EvolutionTarget> {
  return request<EvolutionTarget>(
    workspaceTargetsPath(workspaceId, `/${encodeURIComponent(id)}`),
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
}

/**
 * Delete one evolution target when no active run references it.
 * @param workspaceId Route workspace identifier.
 * @param id Stable target identifier.
 * @returns No value.
 */
export function deleteEvolutionTarget(
  workspaceId: string,
  id: string,
): Promise<void> {
  return request<void>(
    workspaceTargetsPath(workspaceId, `/${encodeURIComponent(id)}`),
    { method: "DELETE" },
  );
}

/**
 * Read remote versions and the configured baseline for one target.
 * @param workspaceId Route workspace identifier.
 * @param id Stable target identifier.
 * @returns Sorted remote tags and the persisted default ref.
 */
export function listEvolutionTargetVersions(
  workspaceId: string,
  id: string,
): Promise<EvolutionTargetVersions> {
  return request<EvolutionTargetVersions>(
    workspaceTargetsPath(workspaceId, `/${encodeURIComponent(id)}/versions`),
  );
}
