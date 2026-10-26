import type {
  SessionListItem,
  SessionListResponse,
  SessionTree,
} from "@harness/contracts";

import { request } from "./http";

/** Server-side filters accepted by the session browser. */
export type SessionStatusFilter = "all" | "ok" | "problem" | "partial" | "fail";

/** Stable server-side session order. */
export type SessionSort = "latest" | "userTurns" | "messages" | "agents";

/** Query values persisted in the session browser URL. */
export type SessionFilters = {
  q?: string;
  status?: SessionStatusFilter;
  sort?: SessionSort;
  limit?: number;
};

/**
 * List root sessions using server-side filtering and ordering.
 * @param filters Current search, status, sort, and limit values.
 * @returns Current-page session cards in server order.
 */
export function listSessions(filters: SessionFilters = {}): Promise<SessionListResponse> {
  const query = new URLSearchParams();
  for (const key of ["q", "status", "sort", "limit"] as const) {
    const value = filters[key];
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return request<SessionListResponse>(`/api/sessions${suffix}`);
}

/**
 * Read one root-session overview.
 * @param sessionId Root session identifier.
 * @returns Session overview and whole-tree statistics.
 */
export function getSession(sessionId: string): Promise<SessionListItem> {
  return request<SessionListItem>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
}

/**
 * Read the canonical flat Agent tree for one root session.
 * @param sessionId Root session identifier.
 * @returns Flat Agent nodes and anchored problem references.
 */
export function getSessionTree(sessionId: string): Promise<SessionTree> {
  return request<SessionTree>(
    `/api/sessions/${encodeURIComponent(sessionId)}/tree`,
  );
}
