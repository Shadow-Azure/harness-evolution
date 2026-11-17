import type {
  AttributionDetail,
  AttributionPage,
  BadCase,
  BadCaseAnalysis,
  ProbeReport,
} from "@harness/contracts";

import { request } from "./http";

/**
 * Build the legacy attribution path for one problem.
 *
 * The attribution projection is still served by the compatibility endpoint,
 * which filters by the caller's visible workspaces; the workspace id remains
 * part of the cache key so two workspaces never share the row.
 * @param badCaseId Stable external problem identifier.
 * @param sessionId Optional route Session used for deep-link ownership.
 * @returns Request path with the optional ownership guard.
 */
function analysisPath(badCaseId: string, sessionId?: string | null): string {
  const path = `/api/bad-cases/${encodeURIComponent(badCaseId)}/analysis`;
  if (!sessionId) return path;
  return `${path}?sessionId=${encodeURIComponent(sessionId)}`;
}

/**
 * Read one problem only when it belongs to the route workspace.
 * @param workspaceId Route workspace identifier.
 * @param badCaseId Stable external problem identifier.
 * @returns Complete public problem.
 */
export function getBadCase(
  workspaceId: string,
  badCaseId: string,
): Promise<BadCase> {
  return request<BadCase>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/bad-cases/${encodeURIComponent(badCaseId)}`,
  );
}

/**
 * Read the status-specific attribution view for one problem.
 * @param badCaseId Stable external problem identifier.
 * @param sessionId Session identifier from the route.
 * @returns Analysis state, including the unanalyzed placeholder.
 */
export function getBadCaseAnalysis(
  badCaseId: string,
  sessionId?: string | null,
): Promise<BadCaseAnalysis> {
  return request<BadCaseAnalysis>(analysisPath(badCaseId, sessionId));
}

/**
 * Read one page of a problem's object/revision attributions.
 *
 * The workspace is part of the path so a page can never cross space
 * boundaries; the backend owns the stable newest-first ordering.
 * @param workspaceId Route workspace identifier.
 * @param badCaseId Stable external problem identifier.
 * @param page One-based page number.
 * @param pageSize Rows per page; the folded list uses the backend default of two.
 * @returns One page plus the reachable row total.
 */
export function getAttributionPage(
  workspaceId: string,
  badCaseId: string,
  page: number,
  pageSize = 2,
): Promise<AttributionPage> {
  const query = new URLSearchParams({
    page: String(page),
    pageSize: String(pageSize),
  });
  return request<AttributionPage>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/bad-cases/${encodeURIComponent(badCaseId)}/attributions?${query.toString()}`,
  );
}

/**
 * Read one attribution only while it is linked to the requested problem.
 * @param workspaceId Route workspace identifier.
 * @param badCaseId Stable external problem identifier.
 * @param attributionId Stable attribution deep-link identifier.
 * @returns Complete attribution detail.
 */
export function getAttribution(
  workspaceId: string,
  badCaseId: string,
  attributionId: string,
): Promise<AttributionDetail> {
  return request<AttributionDetail>(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/bad-cases/${encodeURIComponent(badCaseId)}/attributions/${encodeURIComponent(attributionId)}`,
  );
}

/**
 * Read one root-cause report.
 * @param probeId Stable external probe identifier.
 * @returns Root-cause description and Markdown reasoning.
 */
export function getProbe(probeId: string): Promise<ProbeReport> {
  return request<ProbeReport>(
    `/api/probes/${encodeURIComponent(probeId)}`,
  );
}
