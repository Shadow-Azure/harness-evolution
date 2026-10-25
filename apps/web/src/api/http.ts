import type { ErrorResponse } from "@harness/contracts";

/** Normalized browser API failure carrying the unified error code. */
export class ApiError extends Error {
  /**
   * Create a browser API error.
   * @param status HTTP status, or zero when the request did not complete.
   * @param code Stable error code used by callers.
   * @param message Human-readable failure description.
   * @param details Optional sanitized validation or domain details.
   */
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions<T> = {
  acceptedStatuses?: readonly number[];
  validate?: (payload: unknown, status: number) => T;
};

let accessTokenProvider = (): string | null => null;
let refreshHandler: (() => Promise<boolean>) | null = null;
let authExpiredHandler: ((redirect: string) => void) | null = null;
let passwordChangeHandler: ((redirect: string) => void) | null = null;
let refreshPromise: Promise<boolean> | null = null;

/**
 * Set the access-token source without coupling transport to Pinia.
 * @param provider Callback returning the current in-memory access token.
 * @returns No value.
 */
export function setAccessTokenProvider(provider: () => string | null): void {
  accessTokenProvider = provider;
}

/**
 * Set the single-flight refresh callback.
 * @param handler Callback that rotates the cookie and updates the access token.
 * @returns No value.
 */
export function setRefreshHandler(handler: () => Promise<boolean>): void {
  refreshHandler = handler;
}

/**
 * Set the callback used when refresh cannot recover the session.
 * @param handler Callback that clears auth and navigates with a return path.
 * @returns No value.
 */
export function setAuthExpiredHandler(handler: (redirect: string) => void): void {
  authExpiredHandler = handler;
}

/**
 * Set the callback used for stale forced-password-change state.
 * @param handler Callback that marks the user and navigates to change-password.
 * @returns No value.
 */
export function setPasswordChangeHandler(handler: (redirect: string) => void): void {
  passwordChangeHandler = handler;
}

/**
 * Clear injected transport callbacks between application and test lifetimes.
 * @returns No value.
 */
export function resetHttpAuthHandlers(): void {
  accessTokenProvider = () => null;
  refreshHandler = null;
  authExpiredHandler = null;
  passwordChangeHandler = null;
  refreshPromise = null;
}

function currentAppPath(): string {
  if (typeof window === "undefined") {
    return "/";
  }
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

function headersFor(init: RequestInit | undefined): Headers {
  const headers = new Headers(init?.headers);
  if (init?.body !== undefined && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const token = accessTokenProvider();
  if (token) {
    headers.set("authorization", `Bearer ${token}`);
  }
  return headers;
}

async function decodeFailure(response: Response): Promise<ApiError> {
  const fallback = `API returned HTTP ${response.status}`;
  try {
    const body = (await response.json()) as ErrorResponse;
    const error = body.error;
    if (error?.code && error.message) {
      return new ApiError(response.status, error.code, error.message, error.details);
    }
  } catch {
    // Non-JSON gateway and proxy errors retain a stable local code.
  }
  return new ApiError(response.status, "HTTP_ERROR", fallback);
}

async function refreshOnce(): Promise<boolean> {
  if (!refreshHandler) {
    return false;
  }
  refreshPromise ??= refreshHandler().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

function isPublicAuthRequest(path: string): boolean {
  return path === "/api/auth/login" || path === "/api/auth/refresh";
}

async function execute<T>(
  path: string,
  init: RequestInit | undefined,
  options: RequestOptions<T> | undefined,
  retried: boolean,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers: headersFor(init) });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "API is unreachable");
  }

  const acceptedStatuses = options?.acceptedStatuses ?? [200, 201, 204];
  if (!acceptedStatuses.includes(response.status)) {
    const error = await decodeFailure(response);
    if (
      error.status === 401 &&
      error.code !== "AUTH_INVALID" &&
      !isPublicAuthRequest(path)
    ) {
      if (!retried) {
        const refreshed = await refreshOnce();
        if (refreshed) {
          return execute<T>(path, init, options, true);
        }
      }
      authExpiredHandler?.(currentAppPath());
    }
    if (error.code === "PASSWORD_CHANGE_REQUIRED" && passwordChangeHandler) {
      passwordChangeHandler(currentAppPath());
    }
    throw error;
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(response.status, "INVALID_JSON", "API returned invalid JSON");
  }
  return options?.validate
    ? options.validate(payload, response.status)
    : (payload as T);
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
  options?: RequestOptions<T>,
): Promise<T> {
  return execute<T>(path, init, options, false);
}
