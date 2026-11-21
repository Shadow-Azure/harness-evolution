import { useQuery } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter } from "vue";

import { listEvolutionRuns } from "../api/evolutionRuns";
import { queryKeys } from "../api/queryKeys";

/**
 * Read the backend-owned evolution run-list projection of one workspace.
 * @param workspaceId Workspace route identifier.
 * @returns Query state for the grouped run list.
 */
export function useEvolutionRuns(workspaceId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.evolutionRuns(toValue(workspaceId))),
    queryFn: () => listEvolutionRuns(toValue(workspaceId)),
    enabled: computed(() => toValue(workspaceId).length > 0),
    refetchInterval: (query) => query.state.data?.running.some(run => run.controlState === "pause_requested")
      ? 1_000 : query.state.data?.running.length ? 15_000 : false,
  });
}
