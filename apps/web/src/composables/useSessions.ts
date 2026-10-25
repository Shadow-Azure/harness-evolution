import { useQuery } from "@tanstack/vue-query";
import { computed, type Ref } from "vue";

import {
  getSession,
  getSessionTree,
  listSessions,
  type SessionFilters,
} from "../api/sessions";
import { queryKeys } from "../api/queryKeys";

/**
 * Query root sessions with URL-derived filters.
 * @param filters Reactive server-side filters.
 * @returns Session-list query state.
 */
export function useSessionList(filters: Ref<SessionFilters>) {
  return useQuery({
    queryKey: computed(() => queryKeys.sessionList(filters.value)),
    queryFn: () => listSessions(filters.value),
  });
}

/**
 * Query one selected session overview.
 * @param sessionId Reactive root-session identifier, or null when unselected.
 * @returns Session-overview query state.
 */
export function useSessionSummary(sessionId: Ref<string | null>) {
  return useQuery({
    enabled: computed(() => Boolean(sessionId.value)),
    queryKey: computed(() =>
      sessionId.value
        ? queryKeys.session(sessionId.value)
        : (["sessions", "detail", "empty"] as const),
    ),
    queryFn: () => getSession(sessionId.value as string),
  });
}

/**
 * Query the Agent execution tree for a selected root session.
 * @param sessionId Reactive root-session identifier, or null when unselected.
 * @returns Session-tree query state.
 */
export function useSessionTree(sessionId: Ref<string | null>) {
  return useQuery({
    enabled: computed(() => Boolean(sessionId.value)),
    queryKey: computed(() =>
      sessionId.value
        ? queryKeys.sessionTree(sessionId.value)
        : (["sessions", "tree", "empty"] as const),
    ),
    queryFn: () => getSessionTree(sessionId.value as string),
  });
}
