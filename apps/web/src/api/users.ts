import type { UserListResponse } from "@harness/contracts";

import { request } from "./http";

/**
 * List every user in the single organization.
 *
 * Only the global administrator may call this endpoint; the workspace creation
 * dialog uses it to pick initial space administrators without introducing a
 * separate user-directory page.
 * @returns Public user fields in server order.
 */
export function listUsers(): Promise<UserListResponse> {
  return request<UserListResponse>("/api/users");
}
