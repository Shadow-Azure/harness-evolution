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
 * @param page One-based page for the server-paged steps.
 * @param pageSize Rows per page for the server-paged steps.
 * @returns Query state for the selected step.
 */
export function useEvolutionRunStep(
  workspaceId: MaybeRefOrGetter<string>,
  runId: MaybeRefOrGetter<string>,
  stepKey: MaybeRefOrGetter<EvolutionStepKey>,
  enabled: MaybeRefOrGetter<boolean>,
  page?: MaybeRefOrGetter<number | undefined>,
  pageSize?: MaybeRefOrGetter<number | undefined>,
) {
  const currentPage = () => (page === undefined ? undefined : toValue(page));
  const currentPageSize = () =>
    pageSize === undefined ? undefined : toValue(pageSize);
  return useQuery({
    queryKey: computed(() =>
      queryKeys.evolutionRunStep(
        toValue(workspaceId),
        toValue(runId),
        toValue(stepKey),
        currentPage(),
        currentPageSize(),
      ),
    ),
    queryFn: () =>
      getEvolutionRunStep(
        toValue(workspaceId),
        toValue(runId),
        toValue(stepKey),
        currentPage(),
        currentPageSize(),
      ),
    enabled: computed(() => toValue(enabled)),
  });
}
