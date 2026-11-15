import { useQuery } from "@tanstack/vue-query";
import type { MaybeRefOrGetter } from "vue";
import { computed, toValue } from "vue";
import type { EvolutionStepKey } from "@harness/contracts";

import { getEvolutionRunStep } from "../api/evolutionRuns";
import { queryKeys } from "../api/queryKeys";

/**
 * Read only the step selected by the detail route.
 * @param workspaceId Workspace route identifier.
 * @param runId Evolution run identifier.
 * @param stepKey Stable selected step key.
 * @param enabled Whether the step has been reached and may be requested.
 * @returns Query state for the selected step.
 */
export function useEvolutionRunStep(
  workspaceId: MaybeRefOrGetter<string>,
  runId: MaybeRefOrGetter<string>,
  stepKey: MaybeRefOrGetter<EvolutionStepKey>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.evolutionRunStep(
        toValue(workspaceId),
        toValue(runId),
        toValue(stepKey),
      ),
    ),
    queryFn: () =>
      getEvolutionRunStep(toValue(workspaceId), toValue(runId), toValue(stepKey)),
    enabled: computed(() => toValue(enabled)),
  });
}
