import { useQuery } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter, type Ref } from "vue";

import {
  getAttribution,
  getAttributionPage,
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
 * Query one folded-list page of a problem's object attributions.
 * @param workspaceId Workspace route identifier; keeps the cache space-local.
 * @param badCaseId Problem whose folded group is expanded.
 * @param page One-based page number maintained by the expanded group.
 * @param pageSize Rows per page; the folded list shows two.
 * @returns One deterministic attribution page.
 */
export function useAttributionPage(
  workspaceId: MaybeRefOrGetter<string>,
  badCaseId: MaybeRefOrGetter<string>,
  page: Ref<number>,
  pageSize = 2,
) {
  return useQuery({
    enabled: computed(
      () =>
        toValue(badCaseId).length > 0 &&
        toValue(workspaceId).length > 0 &&
        page.value > 0,
    ),
    queryKey: computed(() =>
      queryKeys.attributionPage(
        toValue(workspaceId),
        toValue(badCaseId),
        Math.max(1, page.value),
        pageSize,
      ),
    ),
    queryFn: () =>
      getAttributionPage(
        toValue(workspaceId),
        toValue(badCaseId),
        Math.max(1, page.value),
        pageSize,
      ),
    retry: false,
  });
}

/**
 * Read every attribution of the selected case for the detail navigator.
 *
 * The list endpoint caps a page at fifty rows, so a case with more rows needs
 * a bounded follow-up read before `N / total` and `at` resolution agree with
 * the paged sidebar.
 * @param workspaceId Workspace route identifier; keeps the cache space-local.
 * @param badCaseId Reactive selected case, or null when nothing is selected.
 * @returns Complete newest-first attribution list.
 */
export function useAttributions(
  workspaceId: MaybeRefOrGetter<string>,
  badCaseId: Ref<string | null>,
) {
  return useQuery({
    enabled: computed(
      () => Boolean(badCaseId.value) && toValue(workspaceId).length > 0,
    ),
    queryKey: computed(() =>
      queryKeys.attributions(
        toValue(workspaceId),
        badCaseId.value ?? "empty",
      ),
    ),
    queryFn: async () => {
      const workspace = toValue(workspaceId);
      const caseId = badCaseId.value as string;
      const first = await getAttributionPage(workspace, caseId, 1, 50);
      const items = [...first.items];
      const pages = Math.ceil(first.total / 50);
      for (let page = 2; page <= pages; page += 1) {
        const next = await getAttributionPage(workspace, caseId, page, 50);
        if (next.items.length === 0) break;
        items.push(...next.items);
      }
      return items;
    },
    retry: false,
  });
}

/**
 * Query one attribution detail after its `at` deep link has been resolved.
 * @param workspaceId Workspace route identifier; keeps the cache space-local.
 * @param badCaseId Owning problem identifier.
 * @param attributionId Reactive selected attribution, or null.
 * @returns Complete attribution detail with trigger evidence.
 */
export function useAttribution(
  workspaceId: MaybeRefOrGetter<string>,
  badCaseId: Ref<string | null>,
  attributionId: Ref<string | null>,
) {
  return useQuery({
    enabled: computed(
      () =>
        Boolean(badCaseId.value) &&
        Boolean(attributionId.value) &&
        toValue(workspaceId).length > 0,
    ),
    queryKey: computed(() =>
      queryKeys.attribution(
        toValue(workspaceId),
        badCaseId.value ?? "empty",
        attributionId.value ?? "empty",
      ),
    ),
    queryFn: () =>
      getAttribution(
        toValue(workspaceId),
        badCaseId.value as string,
        attributionId.value as string,
      ),
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
