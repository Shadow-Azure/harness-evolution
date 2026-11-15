import type { SessionFilters } from "./sessions";

/**
 * Central query-key factories used for domain invalidation.
 *
 * Every workspace-owned key starts with `["ws", workspaceId]` so switching
 * workspaces cannot hit another workspace's cached rows and the old tree can
 * be invalidated with one prefix.
 */
export const queryKeys = {
  health: ["health"] as const,
  /** Current user plus every visible workspace; the single V2 bootstrap entry. */
  authSession: ["auth", "session"] as const,
  workspaces: () => ["ws"] as const,
  workspace: (workspaceId: string) => ["ws", workspaceId] as const,
  admin: (workspaceId: string) => ["ws", workspaceId, "admin"] as const,
  adminMembers: (workspaceId: string) =>
    ["ws", workspaceId, "admin", "members"] as const,
  adminMemberCandidates: (workspaceId: string, query: string) =>
    ["ws", workspaceId, "admin", "member-candidates", query] as const,
  adminCredentials: (workspaceId: string) =>
    ["ws", workspaceId, "admin", "credentials"] as const,
  users: () => ["users"] as const,
  sessions: (workspaceId: string) => ["ws", workspaceId, "sessions"] as const,
  sessionList: (workspaceId: string, filters: SessionFilters) =>
    ["ws", workspaceId, "sessions", filters] as const,
  session: (workspaceId: string, sessionId: string) =>
    ["ws", workspaceId, "session", sessionId] as const,
  sessionTree: (workspaceId: string, sessionId: string) =>
    ["ws", workspaceId, "session", sessionId, "tree"] as const,
  sessionBadCases: (workspaceId: string, sessionId: string) =>
    ["ws", workspaceId, "session", sessionId, "bad-cases"] as const,
  badCase: (workspaceId: string, badCaseId: string, sessionId?: string) =>
    ["ws", workspaceId, "case", badCaseId, "detail", sessionId ?? "unscoped"] as const,
  badCaseAnalysis: (workspaceId: string, badCaseId: string, sessionId?: string) =>
    ["ws", workspaceId, "case", badCaseId, "analysis", sessionId ?? "unscoped"] as const,
  probe: (workspaceId: string, probeId: string) =>
    ["ws", workspaceId, "probe", probeId] as const,
  acquisitionStatus: ["acquisition", "status"] as const,
  evolutionRuns: (workspaceId: string) =>
    ["ws", workspaceId, "evolution", "runs"] as const,
  evolutionRun: (workspaceId: string, runId: string) =>
    ["ws", workspaceId, "evolution", "runs", runId] as const,
  evolutionRunStep: (workspaceId: string, runId: string, stepKey: string) =>
    ["ws", workspaceId, "evolution", "runs", runId, "steps", stepKey] as const,
  evolutionRunEvents: (workspaceId: string, runId: string, level: string) =>
    ["ws", workspaceId, "evolution", "runs", runId, "events", level] as const,
  evolutionTargets: (workspaceId: string) =>
    ["ws", workspaceId, "evolution", "targets"] as const,
  evolutionTargetVersions: (workspaceId: string, targetId: string) =>
    ["ws", workspaceId, "evolution", "targets", targetId, "versions"] as const,
  catalogs: (workspaceId: string) =>
    ["ws", workspaceId, "catalogs"] as const,
  targetCatalog: (workspaceId: string) =>
    ["ws", workspaceId, "catalogs", "targets"] as const,
  modelCatalog: (workspaceId: string) =>
    ["ws", workspaceId, "catalogs", "models"] as const,
};
