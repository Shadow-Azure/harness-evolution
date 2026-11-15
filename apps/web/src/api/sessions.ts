import type {
  BadCaseListResponse,
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

function workspaceSessionPath(workspaceId: string, suffix = ""): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/sessions${suffix}`;
}

/**
 * List root sessions projected from one workspace's bad cases.
 * @param workspaceId Route workspace identifier.
 * @param filters Current search, status, sort, and limit values.
 * @returns Current-page session cards in server order.
 */
export function listSessions(
  workspaceId: string,
  filters: SessionFilters = {},
): Promise<SessionListResponse> {
  const query = new URLSearchParams();
  for (const key of ["q", "status", "sort", "limit"] as const) {
    const value = filters[key];
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return request<SessionListResponse>(workspaceSessionPath(workspaceId, suffix));
}

/**
 * Read one workspace-projected root-session overview.
 * @param workspaceId Route workspace identifier.
 * @param sessionId Root session identifier.
 * @returns Session overview and whole-tree statistics.
 */
export function getSession(
  workspaceId: string,
  sessionId: string,
): Promise<SessionListItem> {
  return request<SessionListItem>(
    workspaceSessionPath(workspaceId, `/${encodeURIComponent(sessionId)}`),
  );
}

/**
 * Read the canonical flat Agent tree for one workspace-projected session.
 * @param workspaceId Route workspace identifier.
 * @param sessionId Root session identifier.
 * @returns Flat Agent nodes and the workspace's anchored problem references.
 */
export function getSessionTree(
  workspaceId: string,
  sessionId: string,
): Promise<SessionTree> {
  return request<SessionTree>(
    workspaceSessionPath(workspaceId, `/${encodeURIComponent(sessionId)}/tree`),
  );
}

/**
 * Read the problems of one root session inside a workspace.
 * @param workspaceId Route workspace identifier.
 * @param sessionId Root session identifier.
 * @returns Problem cards carrying five-state attribution and anchor data.
 */
export function listSessionBadCases(
  workspaceId: string,
  sessionId: string,
): Promise<BadCaseListResponse> {
  return request<BadCaseListResponse>(
    workspaceSessionPath(
      workspaceId,
      `/${encodeURIComponent(sessionId)}/bad-cases`,
    ),
  );
}
