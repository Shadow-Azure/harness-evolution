import type {
  EvolutionStep,
  EvolutionStepKey,
  EvolutionRunDetail,
  EvolutionRunList,
  ProbeQueryRequest,
  ProbeQueryResult,
  RunAccepted,
} from "@harness/contracts";

import { request } from "./http";

/**
 * Read backend-grouped evolution runs in backend order.
 * @returns Running and history groups.
 */
export function listEvolutionRuns(): Promise<EvolutionRunList> {
  return request<EvolutionRunList>("/api/evolution/runs");
}

/**
 * Read one run detail shell with workspace and backend-owned step states.
 * @param runId Evolution run identifier.
 * @returns The complete run detail contract.
 */
export function getEvolutionRunDetail(runId: string): Promise<EvolutionRunDetail> {
  return request<EvolutionRunDetail>(
    `/api/evolution/runs/${encodeURIComponent(runId)}`,
  );
}

/**
 * Read one reached step projection for an evolution run.
 * @param runId Evolution run identifier.
 * @param key Stable step key selected in the detail route.
 * @returns The key-discriminated step payload.
 */
export function getEvolutionRunStep(
  runId: string,
  key: EvolutionStepKey,
): Promise<EvolutionStep> {
  return request<EvolutionStep>(
    `/api/evolution/runs/${encodeURIComponent(runId)}/steps/${key}`,
  );
}

const LAUNCH_STATUSES = [200, 202] as const;

/**
 * Preview probe hits for one wizard condition.
 * @param body Wizard filter condition.
 * @returns Hit statistics plus the requested probe page.
 */
export function queryProbeHits(
  body: ProbeQueryRequest,
): Promise<ProbeQueryResult> {
  return request<ProbeQueryResult>("/api/evolution/probes/query", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Start one full evolution run after backend validation.
 * @param body Wizard filter condition with `mode: "full"`.
 * @returns Accepted run and job identifiers in preparing state.
 */
export function startEvolutionRun(body: ProbeQueryRequest): Promise<RunAccepted> {
  return request<RunAccepted>(
    "/api/evolution/runs",
    { method: "POST", body: JSON.stringify(body) },
    { acceptedStatuses: LAUNCH_STATUSES },
  );
}

/**
 * Start one cluster-only preview run.
 * @param body Wizard filter condition with `mode: "cluster_only"`.
 * @returns Accepted run and job identifiers in preparing state.
 */
export function startClusterPreview(
  body: ProbeQueryRequest,
): Promise<RunAccepted> {
  return request<RunAccepted>(
    "/api/evolution/cluster-previews",
    { method: "POST", body: JSON.stringify(body) },
    { acceptedStatuses: LAUNCH_STATUSES },
  );
}
