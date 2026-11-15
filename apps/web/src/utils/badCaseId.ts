const SHORT_BAD_CASE_ID_LENGTH = 8;

/**
 * Render the stable short form of a real bad-case ID.
 * @param badCaseId Real bad-case identifier.
 * @returns First eight characters, or the full value when shorter.
 */
export function shortBadCaseId(badCaseId: string): string {
  return badCaseId.slice(0, SHORT_BAD_CASE_ID_LENGTH);
}

/**
 * Build the canonical in-app link for a problem description or attribution.
 * @param workspaceId Workspace that owns the Session.
 * @param sessionId Session that owns the problem.
 * @param badCaseId Real problem identifier.
 * @param tab Detail tab to select after navigation.
 * @returns Session error-detail URL with explicit case and tab state.
 */
export function badCaseDeepLink(
  workspaceId: string,
  sessionId: string,
  badCaseId: string,
  tab: "desc" | "attr" = "desc",
): string {
  const query = new URLSearchParams({
    case: badCaseId,
    tab,
  });
  return `/workspaces/${encodeURIComponent(workspaceId)}/sessions/${encodeURIComponent(sessionId)}/errors?${query.toString()}`;
}
