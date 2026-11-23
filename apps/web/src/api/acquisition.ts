import type {
  AcquisitionStatusResponse,
  JobResponse,
  SyncTriggerResponse,
} from "@harness/contracts";

import { request } from "./http";

/**
 * Read durable acquisition progress.
 * @param workspaceId Workspace for the attribution counters.
 * @returns Current pending, processed, and latest batch state.
 */
export function getAcquisitionStatus(workspaceId?: string): Promise<AcquisitionStatusResponse> {
  const query = workspaceId ? `?workspaceId=${encodeURIComponent(workspaceId)}` : "";
  return request<AcquisitionStatusResponse>(`/api/acquisition/status${query}`);
}

/**
 * Request one administrator-owned sync.
 * @returns The queued/reused job or the explicit no-work response.
 */
export function triggerSync(): Promise<SyncTriggerResponse> {
  return request<SyncTriggerResponse>("/api/acquisition/sync", {
    method: "POST"
  }, {
    acceptedStatuses: [200, 202]
  });
}

/**
 * Read one durable job's terminal state.
 * @param jobId Stable job identifier.
 * @returns Latest durable job record.
 */
export function getJob(jobId: string): Promise<JobResponse> {
  return request<JobResponse>(`/api/jobs/${encodeURIComponent(jobId)}`);
}
