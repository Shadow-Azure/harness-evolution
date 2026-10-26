import type {
  BadCase,
  BadCaseAnalysis,
  ProbeReport,
} from "@harness/contracts";

import { request } from "./http";

function ownedBadCasePath(
  badCaseId: string,
  sessionId?: string | null,
  suffix = "",
): string {
  const path = `/api/bad-cases/${encodeURIComponent(badCaseId)}${suffix}`;
  if (!sessionId) return path;
  return `${path}?sessionId=${encodeURIComponent(sessionId)}`;
}

/**
 * Read one problem and enforce its Session ownership when a Session is known.
 * @param badCaseId Stable external problem identifier.
 * @param sessionId Session identifier from the route.
 * @returns Complete public problem.
 */
export function getBadCase(
  badCaseId: string,
  sessionId?: string | null,
): Promise<BadCase> {
  return request<BadCase>(ownedBadCasePath(badCaseId, sessionId));
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
  return request<BadCaseAnalysis>(
    ownedBadCasePath(badCaseId, sessionId, "/analysis"),
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
