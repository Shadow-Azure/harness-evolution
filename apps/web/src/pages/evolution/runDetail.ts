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
