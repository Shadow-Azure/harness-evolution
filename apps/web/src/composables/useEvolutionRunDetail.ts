import { useQuery } from "@tanstack/vue-query";
import type { MaybeRefOrGetter } from "vue";
import { computed, toValue } from "vue";

import { getEvolutionRunDetail } from "../api/evolutionRuns";
import { queryKeys } from "../api/queryKeys";

/**
 * Read the backend-owned run shell with workspace and stepper state.
 * @param runId Evolution run identifier.
 * @returns Query state for one run detail.
 */
export function useEvolutionRunDetail(runId: MaybeRefOrGetter<string>) {
  return useQuery({
    queryKey: computed(() => queryKeys.evolutionRun(toValue(runId))),
    queryFn: () => getEvolutionRunDetail(toValue(runId)),
    enabled: computed(() => toValue(runId).length > 0),
  });
}
