import type {
  EvolutionRetryAccepted,
  EvolutionStep,
  EvolutionStepKey,
  EvolutionRunDetail,
  EvolutionRunEventLevel,
  EvolutionRunEventPage,
  EvolutionRunList,
  ProbeQueryRequest,
  ProbeQueryResult,
  RunAccepted,
} from "@harness/contracts";

import { request } from "./http";

function workspaceEvolutionPath(workspaceId: string, suffix: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/evolution${suffix}`;
}

/**
 * Read backend-grouped evolution runs owned by one workspace.
 * @param workspaceId Route workspace identifier.
 * @returns Running and history groups.
 */
export function listEvolutionRuns(
  workspaceId: string,
): Promise<EvolutionRunList> {
  return request<EvolutionRunList>(
    workspaceEvolutionPath(workspaceId, "/runs"),
  );
}

/**
 * Read one run detail shell with workspace and backend-owned step states.
 * @param workspaceId Route workspace identifier.
 * @param runId Evolution run identifier.
 * @returns The complete run detail contract.
 */
export function getEvolutionRunDetail(
  workspaceId: string,
  runId: string,
): Promise<EvolutionRunDetail> {
  return request<EvolutionRunDetail>(
    workspaceEvolutionPath(workspaceId, `/runs/${encodeURIComponent(runId)}`),
  );
}

/** Optional cursor, page size, and severity filter for execution-log replay. */
export interface EvolutionRunEventQuery {
  afterSeq?: number;
  limit?: number;
  level?: EvolutionRunEventLevel;
}

/**
 * Read one stable page of durable evolution events.
 * @param workspaceId Route workspace identifier.
 * @param runId Evolution run identifier.
 * @param query Cursor, page size, and optional level filter.
 * @returns The ordered event page and continuation cursor.
 */
export function listEvolutionRunEvents(
  workspaceId: string,
  runId: string,
  query: EvolutionRunEventQuery = {},
): Promise<EvolutionRunEventPage> {
  const parameters = new URLSearchParams();
  parameters.set("afterSeq", String(query.afterSeq ?? 0));
  parameters.set("limit", String(query.limit ?? 100));
  if (query.level) parameters.set("level", query.level);
  return request<EvolutionRunEventPage>(
    workspaceEvolutionPath(
      workspaceId,
      `/runs/${encodeURIComponent(runId)}/events?${parameters.toString()}`,
    ),
  );
}

/** Default row counts of the two server-paged steps. */
const STEP_PAGE_SIZES: Partial<Record<EvolutionStepKey, number>> = {
  sessions: 4,
  potential: 5,
};

/**
 * Read one reached step projection for an evolution run.
 * @param workspaceId Route workspace identifier.
 * @param runId Evolution run identifier.
 * @param key Stable step key selected in the detail route.
 * @param page One-based row offset for the paged steps, defaulting to the first page.
 * @param pageSize Rows per page, defaulting to 4 for sessions and 5 for potential.
 * @returns The key-discriminated step payload.
 */
export function getEvolutionRunStep(
  workspaceId: string,
  runId: string,
  key: EvolutionStepKey,
  page?: number,
  pageSize?: number,
): Promise<EvolutionStep> {
  const defaultSize = STEP_PAGE_SIZES[key];
  const parameters = new URLSearchParams();
  if (page !== undefined || pageSize !== undefined) {
    parameters.set("page", String(page ?? 1));
    parameters.set("pageSize", String(pageSize ?? defaultSize ?? 1));
  } else if (defaultSize !== undefined) {
    parameters.set("page", "1");
    parameters.set("pageSize", String(defaultSize));
  }
  const query = parameters.toString();
  return request<EvolutionStep>(
    workspaceEvolutionPath(
      workspaceId,
      `/runs/${encodeURIComponent(runId)}/steps/${key}${query ? `?${query}` : ""}`,
    ),
  );
}

const LAUNCH_STATUSES = [200, 202] as const;

/**
 * Preview probe hits for one wizard condition.
 *
 * The compatibility query filters by every workspace visible to the caller;
 * the wizard only offers targets configured in the current workspace.
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
 * Accepted manual retry for one blocked run.
 *
 * Kept as a re-export so callers can import the generated contract from this
 * API module without duplicating its shape.
 */
export type { EvolutionRetryAccepted };

const RETRY_STATUSES = [202] as const;

/**
 * Request one manual retry for a blocked evolution run.
 * @param workspaceId Route workspace identifier.
 * @param runId Evolution run identifier.
 * @returns The accepted retry job and whether an active job was reused.
 */
export function retryEvolutionRun(
  workspaceId: string,
  runId: string,
): Promise<EvolutionRetryAccepted> {
  return request<EvolutionRetryAccepted>(
    workspaceEvolutionPath(
      workspaceId,
      `/runs/${encodeURIComponent(runId)}/retry`,
    ),
    { method: "POST" },
    { acceptedStatuses: RETRY_STATUSES },
  );
}

/**
 * Start one full evolution run after backend validation.
 * @param workspaceId Route workspace identifier.
 * @param body Wizard filter condition with `mode: "full"`.
 * @returns Accepted run and job identifiers in preparing state.
 */
export function startEvolutionRun(
  workspaceId: string,
  body: ProbeQueryRequest,
): Promise<RunAccepted> {
  return request<RunAccepted>(
    workspaceEvolutionPath(workspaceId, "/runs"),
    { method: "POST", body: JSON.stringify(body) },
    { acceptedStatuses: LAUNCH_STATUSES },
  );
}

/**
 * Start one cluster-only preview run.
 * @param workspaceId Route workspace identifier.
 * @param body Wizard filter condition with `mode: "cluster_only"`.
 * @returns Accepted run and job identifiers in preparing state.
 */
export function startClusterPreview(
  workspaceId: string,
  body: ProbeQueryRequest,
): Promise<RunAccepted> {
  return request<RunAccepted>(
    workspaceEvolutionPath(workspaceId, "/cluster-previews"),
    { method: "POST", body: JSON.stringify(body) },
    { acceptedStatuses: LAUNCH_STATUSES },
  );
}
