import { useQuery } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter, type Ref } from "vue";

import {
  getOverviewSources,
  getOverviewSummary,
  getOverviewTrend,
  listOverviewBadCases,
  type OverviewCaseFilters,
  type OverviewFilters,
} from "../api/overview";
import { queryKeys } from "../api/queryKeys";

/**
 * Query the overview header and the workspace's object options.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window and object filters.
 * @returns Overview summary query state.
 */
export function useOverviewSummary(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<OverviewFilters>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewSummary(toValue(workspaceId), filters.value),
    ),
    queryFn: () => getOverviewSummary(toValue(workspaceId), filters.value),
    enabled: computed(() => toValue(workspaceId).length > 0),
  });
}

/**
 * Query the zero-filled self/discovery trend.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window, object, and grain filters.
 * @returns Trend query state.
 */
export function useOverviewTrend(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<OverviewFilters>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewTrend(toValue(workspaceId), filters.value),
    ),
    queryFn: () => getOverviewTrend(toValue(workspaceId), filters.value),
    enabled: computed(() => toValue(workspaceId).length > 0),
  });
}

/**
 * Query the per-object distribution of the current window.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window and object filters.
 * @returns Source-distribution query state.
 */
export function useOverviewSources(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<OverviewFilters>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewSources(toValue(workspaceId), filters.value),
    ),
    queryFn: () => getOverviewSources(toValue(workspaceId), filters.value),
    enabled: computed(() => toValue(workspaceId).length > 0),
  });
}

/**
 * Query one filtered page of workspace bad cases.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window, object, type, and page filters.
 * @returns Bad-case list query state.
 */
export function useOverviewCases(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<OverviewCaseFilters>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewCases(toValue(workspaceId), filters.value),
    ),
    queryFn: () => listOverviewBadCases(toValue(workspaceId), filters.value),
    enabled: computed(() => toValue(workspaceId).length > 0),
  });
}
