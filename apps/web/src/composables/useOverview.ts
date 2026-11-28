import { useQuery } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter, type Ref } from "vue";

import {
  getOverviewSources,
  getOverviewSummary,
  getOverviewTargetDetail,
  getOverviewTargetsTrend,
  getOverviewTrend,
  listAllOverviewTargets,
  listOverviewBadCases,
  listOverviewTargetCases,
  type OverviewCaseFilters,
  type OverviewFilters,
  type TargetCaseFilters,
  type TargetDetailFilters,
  type TargetOverviewFilters,
} from "../api/overview";
import { queryKeys } from "../api/queryKeys";

function activeQuery(
  workspaceId: MaybeRefOrGetter<string>,
  enabled?: MaybeRefOrGetter<boolean>,
) {
  return computed(
    () =>
      toValue(workspaceId).length > 0 &&
      (enabled === undefined || toValue(enabled)),
  );
}

/**
 * Query the overview header and the workspace's object options.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window and object filters.
 * @param enabled Whether the query should run; omitted means always.
 * @returns Overview summary query state.
 */
export function useOverviewSummary(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<OverviewFilters>,
  enabled?: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewSummary(toValue(workspaceId), filters.value),
    ),
    queryFn: () => getOverviewSummary(toValue(workspaceId), filters.value),
    enabled: activeQuery(workspaceId, enabled),
  });
}

/**
 * Query the zero-filled self/discovery trend.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window, object, and grain filters.
 * @param enabled Whether the query should run; omitted means always.
 * @returns Trend query state.
 */
export function useOverviewTrend(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<OverviewFilters>,
  enabled?: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewTrend(toValue(workspaceId), filters.value),
    ),
    queryFn: () => getOverviewTrend(toValue(workspaceId), filters.value),
    enabled: activeQuery(workspaceId, enabled),
  });
}

/**
 * Query the per-object distribution of the current window.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window and object filters.
 * @param enabled Whether the query should run; omitted means always.
 * @returns Source-distribution query state.
 */
export function useOverviewSources(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<OverviewFilters>,
  enabled?: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewSources(toValue(workspaceId), filters.value),
    ),
    queryFn: () => getOverviewSources(toValue(workspaceId), filters.value),
    enabled: activeQuery(workspaceId, enabled),
  });
}

/**
 * Query one filtered page of workspace bad cases.
 *
 * The list keeps the previous result visible while the next page or filter set
 * loads, so paging does not unmount the table and collapse the scroll height.
 * The placeholder is scoped to the workspace: switching spaces must never show
 * another space's cases.
 *
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window, object, type, and page filters.
 * @param enabled Whether the query should run; omitted means always.
 * @returns Bad-case list query state.
 */
export function useOverviewCases(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<OverviewCaseFilters>,
  enabled?: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewCases(toValue(workspaceId), filters.value),
    ),
    queryFn: () => listOverviewBadCases(toValue(workspaceId), filters.value),
    placeholderData: (previousData, previousQuery) => {
      if (!previousData || !previousQuery) return undefined;
      if (previousQuery.queryKey[1] !== toValue(workspaceId)) return undefined;
      return previousData;
    },
    enabled: activeQuery(workspaceId, enabled),
  });
}

/**
 * Query every enabled evolution target of the current window.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window filters.
 * @param enabled Whether the target tab is active.
 * @returns Complete ordered target list and workspace-wide summary.
 */
export function useOverviewTargets(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<TargetOverviewFilters>,
  enabled?: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewTargets(toValue(workspaceId), filters.value),
    ),
    queryFn: () => listAllOverviewTargets(toValue(workspaceId), filters.value),
    enabled: activeQuery(workspaceId, enabled),
  });
}

/**
 * Query the selected targets' zero-filled three-state trend.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window, target, state, and grain filters.
 * @param enabled Whether the target tab is active.
 * @returns Target trend query state.
 */
export function useOverviewTargetTrend(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<TargetOverviewFilters>,
  enabled?: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewTargetTrend(toValue(workspaceId), filters.value),
    ),
    queryFn: () => getOverviewTargetsTrend(toValue(workspaceId), filters.value),
    enabled: activeQuery(workspaceId, enabled),
  });
}

/**
 * Query one filtered page of potential cases under their target versions.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive window, target, source, state, and page filters.
 * @param enabled Whether the target tab is active.
 * @returns Potential-case query state.
 */
export function useOverviewTargetCases(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<TargetCaseFilters>,
  enabled?: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewTargetCases(toValue(workspaceId), filters.value),
    ),
    queryFn: () => listOverviewTargetCases(toValue(workspaceId), filters.value),
    enabled: activeQuery(workspaceId, enabled),
  });
}

/**
 * Query one target's independent version and source analysis.
 * @param workspaceId Workspace route identifier.
 * @param targetId Reactive target identifier, or an empty string when none is selected.
 * @param filters Reactive independent window and version filters.
 * @param enabled Whether the detail card should load.
 * @returns Target detail query state.
 */
export function useOverviewTargetDetail(
  workspaceId: MaybeRefOrGetter<string>,
  targetId: MaybeRefOrGetter<string>,
  filters: Ref<TargetDetailFilters>,
  enabled?: MaybeRefOrGetter<boolean>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.overviewTargetDetail(
        toValue(workspaceId),
        toValue(targetId),
        filters.value,
      ),
    ),
    queryFn: () =>
      getOverviewTargetDetail(
        toValue(workspaceId),
        toValue(targetId),
        filters.value,
      ),
    enabled: computed(
      () =>
        toValue(workspaceId).length > 0 &&
        toValue(targetId).length > 0 &&
        (enabled === undefined || toValue(enabled)),
    ),
  });
}
