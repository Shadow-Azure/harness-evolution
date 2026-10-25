/** Normalized browser API failure carrying the unified error code. */
export class ApiError extends Error {
  /**
   * Create a browser API error.
   * @param status HTTP status, or zero when the request did not complete.
   * @param code Stable error code used by callers.
   * @param message Human-readable failure description.
   */
  constructor(
    readonly status: number,
    readonly code: string,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Request a JSON API resource and normalize transport failures.
 * @template T Expected response contract type.
 * @param path API path beginning with `/api`.
 * @param init Browser fetch options.
 * @param options Request behavior overrides.
 * @returns The decoded contract payload.
 */
export async function request<T>(
  path: string,
  init?: RequestInit,
  options?: { acceptedStatuses?: readonly number[] }
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "API is unreachable");
  }

  const payload = (await response.json()) as T;
  const acceptedStatuses = options?.acceptedStatuses ?? [200];
  if (!acceptedStatuses.includes(response.status)) {
    throw new ApiError(response.status, "HTTP_ERROR", `API returned HTTP ${response.status}`);
  }
  return payload;
}
