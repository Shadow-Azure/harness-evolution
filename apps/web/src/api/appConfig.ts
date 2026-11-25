import type { AppConfigResponse } from "@harness/contracts";

import { ApiError, request } from "./http";

/** Brand copy shipped with the build; used before and without a deployment override. */
export const DEFAULT_BRAND = {
  name: "Harness Evolution",
  subtitle: "轨迹诊断与自进化",
} as const;

/** Brand name and subtitle rendered by every brand surface. */
export type Brand = AppConfigResponse["brand"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isBrand(value: unknown): value is Brand {
  return (
    isRecord(value) &&
    typeof value.name === "string" &&
    value.name.trim().length > 0 &&
    typeof value.subtitle === "string" &&
    value.subtitle.trim().length > 0
  );
}

function decodeAppConfig(payload: unknown, status: number): AppConfigResponse {
  if (isRecord(payload) && isBrand(payload.brand)) {
    return payload as unknown as AppConfigResponse;
  }
  throw new ApiError(
    status,
    "INVALID_RESPONSE",
    "API returned an invalid app-config payload",
  );
}

/**
 * Fetch the public runtime brand configuration.
 * @returns Brand name and subtitle resolved by the API at startup.
 */
export async function fetchAppConfig(): Promise<AppConfigResponse> {
  return request<AppConfigResponse>("/api/app-config", undefined, {
    validate: decodeAppConfig,
  });
}
