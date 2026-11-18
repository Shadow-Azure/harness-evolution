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

/** User-facing labels shared by the trace panel and the case sidebar. */
export const TRACE_STATUS_LABELS: Record<BadCaseTraceStatus, string> = {
  ready: "就绪",
  pending: "未同步",
  syncing: "同步中",
  failed: "同步失败",
  unavailable: "无可用轨迹",
};

/**
 * Translate a trace status into the label shown in the status chip.
 * @param status Derived trace state.
 * @returns Chinese status label.
 */
export function traceStatusLabel(status: BadCaseTraceStatus): string {
  return TRACE_STATUS_LABELS[status];
}

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
