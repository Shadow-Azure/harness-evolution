import type { BadCaseTraceStatus } from "@harness/contracts";

/** Structured trace state returned in a 409/503 error's `details`. */
export type TraceStatusDetails = {
  badCaseId: string;
  sessionId: string;
  title: string;
  objectName: string;
  createdAt: string | null;
  sessionReady: boolean;
  syncStatus: BadCaseTraceStatus;
  lastError: string | null;
  retryable: boolean;
  nextRetryAt: string | null;
  lastAttemptAt: string | null;
};

const TRACE_STATUSES: ReadonlySet<string> = new Set([
  "ready",
  "pending",
  "syncing",
  "failed",
  "unavailable",
]);

function optionalText(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Parse a structured bad-case trace error without trusting the transport shape.
 * @param details Unknown `ApiError.details` payload.
 * @returns Typed status details, or null when this is not a trace-state error.
 */
export function parseTraceStatusDetails(
  details: unknown,
): TraceStatusDetails | null {
  if (!details || typeof details !== "object") return null;
  const value = details as Record<string, unknown>;
  const syncStatus = optionalText(value.syncStatus);
  if (!syncStatus || !TRACE_STATUSES.has(syncStatus)) return null;
  return {
    badCaseId: optionalText(value.badCaseId) ?? "",
    sessionId: optionalText(value.sessionId) ?? "",
    title: optionalText(value.title) ?? "",
    objectName: optionalText(value.objectName) ?? "",
    createdAt: optionalText(value.createdAt),
    sessionReady: value.sessionReady === true,
    syncStatus: syncStatus as BadCaseTraceStatus,
    lastError: optionalText(value.lastError),
    retryable: value.retryable === true,
    nextRetryAt: optionalText(value.nextRetryAt),
    lastAttemptAt: optionalText(value.lastAttemptAt),
  };
}
