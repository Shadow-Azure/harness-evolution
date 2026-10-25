import { ApiError } from "../api/http";

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
  notify(error.message || "当前有任务正在运行");
  return true;
}
