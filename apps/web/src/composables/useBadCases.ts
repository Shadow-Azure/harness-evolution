import { useQuery } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter, type Ref } from "vue";

import {
  getBadCase,
  getBadCaseAnalysis,
  getProbe,
} from "../api/badCases";
import { queryKeys } from "../api/queryKeys";

/**
 * Query one problem inside the route workspace with deep-link Session ownership.
 * @param workspaceId Workspace route identifier.
 * @param badCaseId Reactive problem identifier, or null when unselected.
 * @param sessionId Reactive route Session identifier.
 * @returns Problem-detail query state.
 */
export function useBadCase(
  workspaceId: MaybeRefOrGetter<string>,
  badCaseId: Ref<string | null>,
  sessionId: Ref<string>,
) {
  return useQuery({
    enabled: computed(
      () => Boolean(badCaseId.value) && toValue(workspaceId).length > 0,
    ),
    queryKey: computed(() =>
      queryKeys.badCase(
        toValue(workspaceId),
        badCaseId.value ?? "empty",
        sessionId.value,
      ),
    ),
    queryFn: () =>
      getBadCase(toValue(workspaceId), badCaseId.value as string),
    retry: false,
  });
}

/**
 * Query the attribution state for one selected problem.
 * @param workspaceId Workspace route identifier.
 * @param badCaseId Reactive problem identifier, or null when unselected.
 * @param sessionId Reactive route Session identifier.
 * @returns Analysis query state.
 */
export function useBadCaseAnalysis(
  workspaceId: MaybeRefOrGetter<string>,
  badCaseId: Ref<string | null>,
  sessionId: Ref<string>,
) {
  return useQuery({
    enabled: computed(
      () => Boolean(badCaseId.value) && toValue(workspaceId).length > 0,
    ),
    queryKey: computed(() =>
      queryKeys.badCaseAnalysis(
        toValue(workspaceId),
        badCaseId.value ?? "empty",
        sessionId.value,
      ),
    ),
    queryFn: () =>
      getBadCaseAnalysis(badCaseId.value as string, sessionId.value),
    retry: false,
  });
}

/**
 * Query the root-cause report linked by an analyzed issue.
 * @param workspaceId Workspace route identifier; keeps the cache space-local.
 * @param probeId Reactive probe identifier, or null for unanalyzed/non-issue.
 * @param enabled Whether the attribution tab currently needs the report.
 * @returns Probe query state.
 */
export function useProbe(
  workspaceId: MaybeRefOrGetter<string>,
  probeId: Ref<string | null>,
  enabled: Ref<boolean> = computed(() => true),
) {
  return useQuery({
    enabled: computed(
      () =>
        enabled.value &&
        Boolean(probeId.value) &&
        toValue(workspaceId).length > 0,
    ),
    queryKey: computed(() =>
      queryKeys.probe(toValue(workspaceId), probeId.value ?? "empty"),
    ),
    queryFn: () => getProbe(probeId.value as string),
    retry: false,
  });
}
