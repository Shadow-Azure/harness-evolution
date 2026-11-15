import { useQuery } from "@tanstack/vue-query";
import { computed, toValue, type MaybeRefOrGetter, type Ref } from "vue";

import {
  getSession,
  getSessionTree,
  listSessionBadCases,
  listSessions,
  type SessionFilters,
} from "../api/sessions";
import { queryKeys } from "../api/queryKeys";

/**
 * Query root sessions of one workspace with URL-derived filters.
 * @param workspaceId Workspace route identifier.
 * @param filters Reactive server-side filters.
 * @returns Session-list query state.
 */
export function useSessionList(
  workspaceId: MaybeRefOrGetter<string>,
  filters: Ref<SessionFilters>,
) {
  return useQuery({
    queryKey: computed(() =>
      queryKeys.sessionList(toValue(workspaceId), filters.value),
    ),
    queryFn: () => listSessions(toValue(workspaceId), filters.value),
    enabled: computed(() => toValue(workspaceId).length > 0),
  });
}

/**
 * Query one selected session overview.
 * @param workspaceId Workspace route identifier.
 * @param sessionId Reactive root-session identifier, or null when unselected.
 * @returns Session-overview query state.
 */
export function useSessionSummary(
  workspaceId: MaybeRefOrGetter<string>,
  sessionId: Ref<string | null>,
) {
  return useQuery({
    enabled: computed(
      () => Boolean(sessionId.value) && toValue(workspaceId).length > 0,
    ),
    queryKey: computed(() =>
      queryKeys.session(toValue(workspaceId), sessionId.value ?? "empty"),
    ),
    queryFn: () => getSession(toValue(workspaceId), sessionId.value as string),
  });
}

/**
 * Query the Agent execution tree for a selected root session.
 * @param workspaceId Workspace route identifier.
 * @param sessionId Reactive root-session identifier, or null when unselected.
 * @returns Session-tree query state.
 */
export function useSessionTree(
  workspaceId: MaybeRefOrGetter<string>,
  sessionId: Ref<string | null>,
) {
  return useQuery({
    enabled: computed(
      () => Boolean(sessionId.value) && toValue(workspaceId).length > 0,
    ),
    queryKey: computed(() =>
      queryKeys.sessionTree(toValue(workspaceId), sessionId.value ?? "empty"),
    ),
    queryFn: () =>
      getSessionTree(toValue(workspaceId), sessionId.value as string),
  });
}

/**
 * Query the problem cards for one selected root session.
 * @param workspaceId Workspace route identifier.
 * @param sessionId Reactive root-session identifier, or null when unselected.
 * @returns Session problem-list query state.
 */
export function useSessionBadCases(
  workspaceId: MaybeRefOrGetter<string>,
  sessionId: Ref<string | null>,
) {
  return useQuery({
    enabled: computed(
      () => Boolean(sessionId.value) && toValue(workspaceId).length > 0,
    ),
    queryKey: computed(() =>
      queryKeys.sessionBadCases(
        toValue(workspaceId),
        sessionId.value ?? "empty",
      ),
    ),
    queryFn: () =>
      listSessionBadCases(toValue(workspaceId), sessionId.value as string),
  });
}
