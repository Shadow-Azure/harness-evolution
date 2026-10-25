/** Central query-key factories used for domain invalidation. */
export const queryKeys = {
  health: ["health"] as const,
  sessions: ["sessions"] as const,
  acquisitionStatus: ["acquisition", "status"] as const,
};
