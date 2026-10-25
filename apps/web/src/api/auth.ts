import type {
  ChangePasswordRequest,
  LoginRequest,
  LoginResponse,
  PublicUser,
  RefreshResponse,
} from "@harness/contracts";

import { request } from "./http";

/**
 * Exchange credentials for an access token and backend-managed refresh cookie.
 * @param credentials Username and password supplied by the login form.
 * @returns The authenticated session payload.
 */
export function login(credentials: LoginRequest): Promise<LoginResponse> {
  return request<LoginResponse>("/api/auth/login", {
    body: JSON.stringify(credentials),
    credentials: "include",
    method: "POST",
  });
}

/**
 * Rotate the refresh cookie and obtain a fresh access token.
 * @returns The refreshed token payload.
 */
export function refresh(): Promise<RefreshResponse> {
  return request<RefreshResponse>("/api/auth/refresh", {
    credentials: "include",
    method: "POST",
  });
}

/**
 * Revoke the refresh cookie and clear the browser session on the server.
 * @returns Nothing.
 */
export function logout(): Promise<void> {
  return request<void>("/api/auth/logout", {
    credentials: "include",
    method: "POST",
  });
}

/**
 * Change the authenticated user's password.
 * @param passwords Current and replacement password values.
 * @returns Nothing.
 */
export function changePassword(passwords: ChangePasswordRequest): Promise<void> {
  return request<void>("/api/auth/change-password", {
    body: JSON.stringify(passwords),
    method: "POST",
  });
}

/**
 * Load the current authenticated user.
 * @returns The safe public user fields.
 */
export function me(): Promise<PublicUser> {
  return request<PublicUser>("/api/auth/me");
}
