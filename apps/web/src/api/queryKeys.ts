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
  acquisitionStatus: ["acquisition", "status"] as const,
};
