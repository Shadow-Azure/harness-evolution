import type {
  EvolutionTarget,
  EvolutionTargetList,
  EvolutionTargetVersions,
  EvolutionTargetWrite,
} from "@harness/contracts";

import { request } from "./http";

/**
 * Read every evolution target configuration, including disabled rows.
 * @returns Target configuration collection.
 */
export function listEvolutionTargets(): Promise<EvolutionTargetList> {
  return request<EvolutionTargetList>("/api/evolution/targets");
}

/**
 * Create one evolution target.
 * @param body Mutable target configuration.
 * @returns Persisted target.
 */
export function createEvolutionTarget(
  body: EvolutionTargetWrite,
): Promise<EvolutionTarget> {
  return request<EvolutionTarget>("/api/evolution/targets", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Update one evolution target.
 * @param id Stable target identifier.
 * @param body Mutable target configuration.
 * @returns Updated target.
 */
export function updateEvolutionTarget(
  id: string,
  body: EvolutionTargetWrite,
): Promise<EvolutionTarget> {
  return request<EvolutionTarget>(
    `/api/evolution/targets/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
}

/**
 * Delete one evolution target when no active run references it.
 * @param id Stable target identifier.
 * @returns No value.
 */
export function deleteEvolutionTarget(id: string): Promise<void> {
  return request<void>(`/api/evolution/targets/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

/**
 * Read remote versions and the configured baseline for one target.
 * @param id Stable target identifier.
 * @returns Sorted remote tags and the persisted default ref.
 */
export function listEvolutionTargetVersions(
  id: string,
): Promise<EvolutionTargetVersions> {
  return request<EvolutionTargetVersions>(
    `/api/evolution/targets/${encodeURIComponent(id)}/versions`,
  );
}
