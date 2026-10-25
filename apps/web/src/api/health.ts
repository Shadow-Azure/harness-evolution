import type { HealthResponse } from "@harness/contracts";

import { request } from "./http";

/**
 * Fetch the public API health contract.
 * @returns Canonical health status from the FastAPI service.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health", undefined, { acceptedStatuses: [200, 503] });
}
