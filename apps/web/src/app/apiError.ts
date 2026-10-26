import { ApiError } from "../api/http";

const PAGE_HANDLED_CONFLICT_CODES: ReadonlySet<string> = new Set([
  "BAD_CASE_SESSION_MISMATCH",
  "TARGET_IN_USE",
]);

/**
 * Present a non-blocking 409 conflict through the application notification seam.
 * @param error Failure raised by the shared API transport.
 * @param notify User-facing notification callback.
 * @returns Whether the error was handled as a conflict.
 */
export function presentConflict(
  error: unknown,
  notify: (message: string) => void,
): boolean {
  if (!(error instanceof ApiError) || error.status !== 409) {
    return false;
  }
  if (PAGE_HANDLED_CONFLICT_CODES.has(error.code)) {
    return false;
  }
  notify(error.message || "当前有任务正在运行");
  return true;
}
