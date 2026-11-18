import type {
  OverviewBadCaseListResponse,
  OverviewBadCaseType,
  OverviewGrain,
  OverviewRange,
  OverviewSourceListResponse,
  OverviewSummary,
  OverviewTrendResponse,
  TargetCaseListResponse,
  TargetDetailResponse,
  TargetOverviewListResponse,
  TargetState,
  TargetTrendResponse,
} from "@harness/contracts";

import { request } from "./http";

/** Default page size shared by the overview list and its pager. */
export const OVERVIEW_PAGE_SIZE = 8;

/** Default page size of the evolution-target side list (design 05 §4.18). */
export const TARGET_PAGE_SIZE = 5;

/** Default page size of the potential-case list under the target view. */
export const TARGET_CASE_PAGE_SIZE = 8;

/** Largest page size the overview API accepts in one request. */
const TARGET_PAGE_MAX = 50;

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
  /** Ignore every date boundary and return all reported cases. */
  allTime?: boolean;
  page?: number;
  pageSize?: number;
};

/** Window, target selection, state and paging filters of one target read. */
export type TargetOverviewFilters = {
  /** Inclusive local start date; sent with `to` for a custom window. */
  from?: string;
  /** Inclusive local end date; sent with `from` for a custom window. */
  to?: string;
  /** Quick range, used only when no explicit boundary pair is supplied. */
  range?: OverviewRange;
  /** Evolution target ids; empty or omitted means every enabled target. */
  targets?: string[];
  /** Attribution states; empty or omitted means the full three-state set. */
  states?: TargetState[];
  /** Requested trend grain; only the trend endpoint consumes it. */
  grain?: OverviewGrain;
  /** 1-based page number for the target list or potential-case list. */
  page?: number;
  /** Page size for the target list or potential-case list. */
  pageSize?: number;
};

/** Potential-case list filters, which additionally accept source objects. */
export type TargetCaseFilters = TargetOverviewFilters & {
  /** Object names the bad cases were reported against. */
  objects?: string[];
};

/** One target detail card's independent window and version scope. */
export type TargetDetailFilters = {
  /** Inclusive local start date of the card's independent window. */
  from?: string;
  /** Inclusive local end date of the card's independent window. */
  to?: string;
  /** Quick range used when no explicit boundary pair is supplied. */
  range?: OverviewRange;
  /** Explicit versions; empty selects the newest `versionLimit` versions. */
  versions?: string[];
  /** Newest-version count when `versions` is empty; 0 means every version. */
  versionLimit?: 0 | 5 | 10 | 20;
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
  if (filters.allTime) {
    query.set("allTime", "true");
  } else {
    appendWindow(query, filters);
  }
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

function appendTargets(
  query: URLSearchParams,
  targets: string[] | undefined,
): void {
  if (!targets) return;
  const unique = [...new Set(targets.map((id) => id.trim()).filter(Boolean))];
  if (unique.length > 0) {
    query.set("targets", unique.join(","));
  }
}

function appendStates(
  query: URLSearchParams,
  states: TargetState[] | undefined,
): void {
  if (!states) return;
  const unique = [...new Set(states)];
  if (unique.length > 0) {
    query.set("states", unique.join(","));
  }
}

function appendVersions(
  query: URLSearchParams,
  versions: string[] | undefined,
): void {
  if (!versions) return;
  const unique = [...new Set(versions.map((value) => value.trim()).filter(Boolean))];
  if (unique.length > 0) {
    query.set("versions", unique.join(","));
  }
}

/**
 * Read one evolvable-sorted page of evolution targets plus the summary.
 * @param workspaceId Route workspace identifier.
 * @param filters Window plus target-list paging.
 * @returns One target page and the workspace-wide target summary.
 */
export function getOverviewTargets(
  workspaceId: string,
  filters: TargetOverviewFilters = {},
): Promise<TargetOverviewListResponse> {
  const query = new URLSearchParams();
  appendWindow(query, filters);
  query.set("page", String(filters.page ?? 1));
  query.set("pageSize", String(filters.pageSize ?? TARGET_PAGE_SIZE));
  return request<TargetOverviewListResponse>(
    `${overviewPath(workspaceId, "targets")}${withSuffix(query)}`,
  );
}

/**
 * Read every enabled target of one window, following the API's pages.
 *
 * The target multi-select, side-list pager and detail selector all need the
 * complete ordered list; the overview endpoints cap one page at 50 rows.
 *
 * @param workspaceId Route workspace identifier.
 * @param filters Window filters; target/state filters are not sent here.
 * @returns Every target row and the workspace-wide summary.
 */
export async function listAllOverviewTargets(
  workspaceId: string,
  filters: TargetOverviewFilters = {},
): Promise<TargetOverviewListResponse> {
  const first = await getOverviewTargets(workspaceId, {
    ...filters,
    page: 1,
    pageSize: TARGET_PAGE_MAX,
  });
  const items = [...first.items];
  const pages = Math.ceil(first.total / TARGET_PAGE_MAX);
  for (let page = 2; page <= pages; page += 1) {
    const next = await getOverviewTargets(workspaceId, {
      ...filters,
      page,
      pageSize: TARGET_PAGE_MAX,
    });
    items.push(...next.items);
    if (next.items.length === 0) break;
  }
  return {
    ...first,
    items,
    page: 1,
    pageSize: Math.max(1, items.length),
  };
}

/**
 * Read the selected targets' zero-filled three-state trend.
 * @param workspaceId Route workspace identifier.
 * @param filters Window, target, state, and grain filters.
 * @returns The continuous target series plus the grain actually used.
 */
export function getOverviewTargetsTrend(
  workspaceId: string,
  filters: TargetOverviewFilters = {},
): Promise<TargetTrendResponse> {
  const query = new URLSearchParams();
  appendWindow(query, filters);
  appendTargets(query, filters.targets);
  appendStates(query, filters.states);
  if (filters.grain) {
    query.set("grain", filters.grain);
  }
  return request<TargetTrendResponse>(
    `${overviewPath(workspaceId, "targets/trend")}${withSuffix(query)}`,
  );
}

/**
 * Read one filtered page of potential cases under their target versions.
 * @param workspaceId Route workspace identifier.
 * @param filters Window, target, source, state, and page filters.
 * @returns One page of potential cases plus the authoritative total.
 */
export function listOverviewTargetCases(
  workspaceId: string,
  filters: TargetCaseFilters = {},
): Promise<TargetCaseListResponse> {
  const query = new URLSearchParams();
  appendWindow(query, filters);
  appendTargets(query, filters.targets);
  appendObjects(query, filters.objects);
  appendStates(query, filters.states);
  query.set("page", String(filters.page ?? 1));
  query.set("pageSize", String(filters.pageSize ?? TARGET_CASE_PAGE_SIZE));
  return request<TargetCaseListResponse>(
    `${overviewPath(workspaceId, "targets/cases")}${withSuffix(query)}`,
  );
}

/**
 * Read one target's independent version and source analysis.
 * @param workspaceId Route workspace identifier.
 * @param targetId Evolution target identifier from the route/page state.
 * @param filters Independent window, explicit versions, and version limit.
 * @returns The target's stats, per-version split, and per-source split.
 */
export function getOverviewTargetDetail(
  workspaceId: string,
  targetId: string,
  filters: TargetDetailFilters = {},
): Promise<TargetDetailResponse> {
  const query = new URLSearchParams();
  appendWindow(query, filters);
  appendVersions(query, filters.versions);
  if (filters.versionLimit !== undefined) {
    query.set("versionLimit", String(filters.versionLimit));
  }
  return request<TargetDetailResponse>(
    `${overviewPath(
      workspaceId,
      `targets/${encodeURIComponent(targetId)}/detail`,
    )}${withSuffix(query)}`,
  );
}
