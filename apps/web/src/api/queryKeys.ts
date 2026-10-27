import type { SessionFilters } from "./sessions";

/** Central query-key factories used for domain invalidation. */
export const queryKeys = {
  health: ["health"] as const,
  sessions: ["sessions"] as const,
  sessionList: (filters: SessionFilters) =>
    ["sessions", "list", filters] as const,
  session: (sessionId: string) =>
    ["sessions", "detail", sessionId] as const,
  sessionTree: (sessionId: string) =>
    ["sessions", "tree", sessionId] as const,
  sessionBadCases: (sessionId: string) =>
    ["sessions", "bad-cases", sessionId] as const,
  badCase: (badCaseId: string, sessionId?: string) =>
    ["bad-case", badCaseId, "detail", sessionId ?? "unscoped"] as const,
  badCaseAnalysis: (badCaseId: string, sessionId?: string) =>
    ["bad-case", badCaseId, "analysis", sessionId ?? "unscoped"] as const,
  probe: (probeId: string) =>
    ["probe", probeId] as const,
  acquisitionStatus: ["acquisition", "status"] as const,
  evolutionRuns: ["evolution", "runs"] as const,
  evolutionRun: (runId: string) =>
    ["evolution", "runs", runId] as const,
  evolutionRunStep: (runId: string, stepKey: string) =>
    ["evolution", "runs", runId, "steps", stepKey] as const,
  evolutionRunEvents: (runId: string, level: string) =>
    ["evolution", "runs", runId, "events", level] as const,
  evolutionTargets: ["evolution", "targets"] as const,
  evolutionTargetVersions: (targetId: string) =>
    ["evolution", "targets", targetId, "versions"] as const,
  catalogs: ["catalogs"] as const,
  targetCatalog: ["catalogs", "targets"] as const,
  modelCatalog: ["catalogs", "models"] as const,
};
