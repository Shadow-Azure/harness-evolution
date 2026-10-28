import type { EvolutionRunStep, EvolutionStepKey } from "@harness/contracts";

/** Backend-emitted stepper node; `clickable` gates query and step requests. */
export type RunStep = EvolutionRunStep;

/**
 * Select the first active step, otherwise the last completed step.
 * @param steps Six backend-owned run steps.
 * @returns The stable key to open when no valid query selection exists.
 */
export function defaultRunStepKey(steps: readonly RunStep[]): EvolutionStepKey {
  const active = steps.find((step) => step.status === "active");
  if (active) return active.key;
  const done = [...steps].reverse().find((step) => step.status === "done");
  return done?.key ?? "input";
}

/**
 * Resolve a route query key against backend-derived clickable state.
 * @param value Query-string value.
 * @param steps Six backend-owned run steps.
 * @returns A valid reached key or the default key.
 */
export function resolveRunStepKey(
  value: unknown,
  steps: readonly RunStep[],
): EvolutionStepKey {
  const candidate = typeof value === "string" ? value : "";
  const match = steps.find((step) => step.key === candidate);
  return match?.clickable ? match.key : defaultRunStepKey(steps);
}

/**
 * Format one backend timestamp in the viewer's local time.
 * @param value ISO-8601 timestamp returned by the backend.
 * @returns `YYYY-MM-DD HH:mm:ss` in local time, or the input when unparsable.
 */
export function formatLocalDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, "0");
  return [
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`,
  ].join(" ");
}

/**
 * Render one run-level push status without misrepresenting local-only runs.
 * @param status Backend run push status.
 * @returns Human-readable status label.
 */
export function workspacePushStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return "待推送";
    case "pushing":
      return "推送中";
    case "succeeded":
      return "推送成功";
    case "failed":
      return "推送失败";
    case "skipped":
      return "已跳过（本地模式）";
    default:
      return status;
  }
}
