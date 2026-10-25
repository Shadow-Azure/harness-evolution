import {
  DATABASE_DIALECTS,
  SERVICE_PHASES,
  type ErrorResponse,
  type HealthResponse,
} from "@harness/contracts";

import { ApiError, request } from "./http";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isHealthResponse(payload: unknown): payload is HealthResponse {
  if (!isRecord(payload) || !isRecord(payload.db)) {
    return false;
  }
  const { db } = payload;
  return (
    payload.service === "harness-evolution" &&
    typeof payload.version === "string" &&
    typeof payload.ok === "boolean" &&
    typeof payload.phase === "string" &&
    SERVICE_PHASES.some((phase) => phase === payload.phase) &&
    typeof db.ok === "boolean" &&
    typeof db.latencyMs === "number" &&
    typeof db.dialect === "string" &&
    DATABASE_DIALECTS.some((dialect) => dialect === db.dialect) &&
    (db.error === undefined || db.error === null || typeof db.error === "string")
  );
}

function isErrorResponse(payload: unknown): payload is ErrorResponse {
  return (
    isRecord(payload) &&
    isRecord(payload.error) &&
    typeof payload.error.code === "string" &&
    typeof payload.error.message === "string"
  );
}

function decodeHealth(payload: unknown, status: number): HealthResponse {
  if (isHealthResponse(payload)) {
    return payload;
  }
  if (isErrorResponse(payload)) {
    throw new ApiError(
      status,
      payload.error.code,
      payload.error.message,
      payload.error.details,
    );
  }
  throw new ApiError(
    status,
    "INVALID_RESPONSE",
    "API returned an invalid health payload",
  );
}

/**
 * Fetch the public API health contract.
 * @returns Canonical health status from the FastAPI service.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health", undefined, {
    acceptedStatuses: [200, 503],
    validate: decodeHealth,
  });
}
