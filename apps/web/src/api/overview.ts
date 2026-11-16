import type {
  OverviewBadCaseListResponse,
  OverviewBadCaseType,
  OverviewGrain,
  OverviewRange,
  OverviewSourceListResponse,
  OverviewSummary,
  OverviewTrendResponse,
} from "@harness/contracts";

import { request } from "./http";

/** Default page size shared by the overview list and its pager. */
export const OVERVIEW_PAGE_SIZE = 8;

/** Inclusive window plus the shared object filter of every overview read. */
export type OverviewFilters = {
  /** Inclusive local start date; sent with `to` for a custom window. */
  from?: string;
  /** Inclusive local end date; sent with `from` for a custom window. */
  to?: string;
  /** Quick range, used only when no explicit boundary pair is supplied. */
  range?: OverviewRange;
  /** Object names; empty or omitted means every object. */
  objects?: string[];
  /** Requested trend grain; only the trend endpoint consumes it. */
  grain?: OverviewGrain;
};

/** One overview list page including its type filter and paging. */
export type OverviewCaseFilters = OverviewFilters & {
  badCaseType?: OverviewBadCaseType;
  page?: number;
  pageSize?: number;
};

function overviewPath(workspaceId: string, suffix: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/overview/${suffix}`;
}

function workspacePath(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/bad-cases`;
}

function withSuffix(query: URLSearchParams): string {
  return query.size ? `?${query.toString()}` : "";
}

function appendObjects(query: URLSearchParams, objects: string[] | undefined): void {
  if (!objects) return;
  const unique = [
    ...new Set(objects.map((name) => name.trim()).filter(Boolean)),
  ];
  if (unique.length > 0) {
    query.set("objects", unique.join(","));
  }
}

function appendWindow(query: URLSearchParams, filters: OverviewFilters): void {
  if (filters.from && filters.to) {
    query.set("from", filters.from);
    query.set("to", filters.to);
    return;
  }
  if (filters.range !== undefined) {
    query.set("range", String(filters.range));
  }
}

/**
 * Read one workspace overview header.
 * @param workspaceId Route workspace identifier.
 * @param filters Window and object filters derived from the URL.
 * @returns Window, totals, and the object options of the workspace.
 */
export function getOverviewSummary(
  workspaceId: string,
  filters: OverviewFilters = {},
): Promise<OverviewSummary> {
  const query = new URLSearchParams();
  appendWindow(query, filters);
  appendObjects(query, filters.objects);
  return request<OverviewSummary>(
    `${overviewPath(workspaceId, "summary")}${withSuffix(query)}`,
  );
}

/**
 * Read the zero-filled self/discovery trend of one workspace.
 * @param workspaceId Route workspace identifier.
 * @param filters Window, object, and grain filters derived from the URL.
 * @returns The continuous series plus the grain the server actually used.
 */
export function getOverviewTrend(
  workspaceId: string,
  filters: OverviewFilters = {},
): Promise<OverviewTrendResponse> {
  const query = new URLSearchParams();
  appendWindow(query, filters);
  appendObjects(query, filters.objects);
  if (filters.grain) {
    query.set("grain", filters.grain);
  }
  return request<OverviewTrendResponse>(
    `${overviewPath(workspaceId, "trend")}${withSuffix(query)}`,
  );
}

/**
 * Read the per-object share of one overview window.
 * @param workspaceId Route workspace identifier.
 * @param filters Window and object filters derived from the URL.
 * @returns Object distribution ordered by total descending.
 */
export function getOverviewSources(
  workspaceId: string,
  filters: OverviewFilters = {},
): Promise<OverviewSourceListResponse> {
  const query = new URLSearchParams();
  appendWindow(query, filters);
  appendObjects(query, filters.objects);
  return request<OverviewSourceListResponse>(
    `${overviewPath(workspaceId, "sources")}${withSuffix(query)}`,
  );
}

/**
 * Read one filtered page of workspace bad cases.
 * @param workspaceId Route workspace identifier.
 * @param filters Window, object, type, and page filters derived from the URL.
 * @returns One page of reported cases plus the filtered total.
 */
export function listOverviewBadCases(
  workspaceId: string,
  filters: OverviewCaseFilters = {},
): Promise<OverviewBadCaseListResponse> {
  const query = new URLSearchParams();
  appendWindow(query, filters);
  appendObjects(query, filters.objects);
  if (filters.badCaseType && filters.badCaseType !== "all") {
    query.set("badCaseType", filters.badCaseType);
  }
  query.set("page", String(filters.page ?? 1));
  query.set("pageSize", String(filters.pageSize ?? OVERVIEW_PAGE_SIZE));
  return request<OverviewBadCaseListResponse>(
    `${workspacePath(workspaceId)}${withSuffix(query)}`,
  );
}
