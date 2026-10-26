import { useQuery } from "@tanstack/vue-query";

import { listEvolutionRuns } from "../api/evolutionRuns";
import { queryKeys } from "../api/queryKeys";

/**
 * Read the backend-owned evolution run-list projection.
 * @returns Query state for the grouped run list.
 */
export function useEvolutionRuns() {
  return useQuery({
    queryKey: queryKeys.evolutionRuns,
    queryFn: listEvolutionRuns,
  });
}
