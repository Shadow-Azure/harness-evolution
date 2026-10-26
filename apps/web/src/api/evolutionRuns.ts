import type { EvolutionRunList } from "@harness/contracts";

import { request } from "./http";

/**
 * Read backend-grouped evolution runs in backend order.
 * @returns Running and history groups.
 */
export function listEvolutionRuns(): Promise<EvolutionRunList> {
  return request<EvolutionRunList>("/api/evolution/runs");
}
