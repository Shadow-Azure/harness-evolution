import { useQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";

import {
  getBadCase,
  getBadCaseAnalysis,
  getProbe,
} from "../api/badCases";
import { queryKeys } from "../api/queryKeys";

/**
 * Query one problem with deep-link Session ownership enforcement.
 * @param badCaseId Reactive problem identifier, or null when unselected.
 * @param sessionId Reactive route Session identifier.
 * @returns Problem-detail query state.
 */
export function useBadCase(
  badCaseId: Ref<string | null>,
  sessionId: Ref<string>,
) {
  return useQuery({
    enabled: computed(() => Boolean(badCaseId.value)),
    queryKey: computed(() =>
      badCaseId.value
        ? queryKeys.badCase(badCaseId.value, sessionId.value)
        : (["bad-case", "empty"] as const),
    ),
    queryFn: () => getBadCase(badCaseId.value as string, sessionId.value),
    retry: false,
  });
}

/**
 * Query the attribution state for one selected problem.
 * @param badCaseId Reactive problem identifier, or null when unselected.
 * @param sessionId Reactive route Session identifier.
 * @returns Analysis query state.
 */
export function useBadCaseAnalysis(
  badCaseId: Ref<string | null>,
  sessionId: Ref<string>,
) {
  return useQuery({
    enabled: computed(() => Boolean(badCaseId.value)),
    queryKey: computed(() =>
      badCaseId.value
        ? queryKeys.badCaseAnalysis(badCaseId.value, sessionId.value)
        : (["bad-case", "analysis", "empty"] as const),
    ),
    queryFn: () =>
      getBadCaseAnalysis(badCaseId.value as string, sessionId.value),
    retry: false,
  });
}

/**
 * Query the root-cause report linked by an analyzed issue.
 * @param probeId Reactive probe identifier, or null for unanalyzed/non-issue.
 * @param enabled Whether the attribution tab currently needs the report.
 * @returns Probe query state.
 */
export function useProbe(
  probeId: Ref<string | null>,
  enabled: Ref<boolean> = computed(() => true),
) {
  return useQuery({
    enabled: computed(() => enabled.value && Boolean(probeId.value)),
    queryKey: computed(() =>
      probeId.value
        ? queryKeys.probe(probeId.value)
        : (["probe", "empty"] as const),
    ),
    queryFn: () => getProbe(probeId.value as string),
    retry: false,
  });
}
