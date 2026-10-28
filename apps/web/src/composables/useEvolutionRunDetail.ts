import type { EvolutionRunDetail } from "@harness/contracts";
import { useQuery } from "@tanstack/vue-query";
import type { MaybeRefOrGetter } from "vue";
import { computed, toValue } from "vue";

import { getEvolutionRunDetail } from "../api/evolutionRuns";
import { queryKeys } from "../api/queryKeys";

/** Resolves the poll cadence from the latest run snapshot. */
export type EvolutionRunRefetchResolver = (
  run: EvolutionRunDetail | undefined,
) => number | false | undefined;

/** Poll cadence for one run snapshot: blocked fallback, active fallback, or off. */
export type EvolutionRunRefetchInterval =
  | number
  | false
  | EvolutionRunRefetchResolver;

/** Optional query behavior for the run-detail snapshot. */
export interface EvolutionRunDetailOptions {
  refetchInterval?: EvolutionRunRefetchInterval;
}

/**
 * Choose the REST polling fallback for one run status.
 *
 * SSE stays the primary live channel for active runs; polling only closes the
 * gaps when the stream is reconnecting. Blocked runs are not subscribed, so
 * they poll faster to pick up the sweeper's automatic retry.
 * @param run Latest run snapshot, or undefined before the first response.
 * @returns Poll interval in milliseconds, or false for terminal states.
 */
export function runDetailRefetchInterval(
  run: EvolutionRunDetail | undefined,
): number | false {
  switch (run?.status) {
    case "blocked":
      return 5_000;
    case "preparing":
    case "running":
      return 15_000;
    default:
      return false;
  }
}

/**
 * Read the backend-owned run shell with workspace and stepper state.
 * @param runId Evolution run identifier.
 * @param options Optional polling cadence for live or blocked runs.
 * @returns Query state for one run detail.
 */
export function useEvolutionRunDetail(
  runId: MaybeRefOrGetter<string>,
  options: EvolutionRunDetailOptions = {},
) {
  const { refetchInterval } = options;
  return useQuery({
    queryKey: computed(() => queryKeys.evolutionRun(toValue(runId))),
    queryFn: () => getEvolutionRunDetail(toValue(runId)),
    enabled: computed(() => toValue(runId).length > 0),
    refetchInterval: (query) =>
      typeof refetchInterval === "function"
        ? refetchInterval(query.state.data)
        : refetchInterval,
  });
}
