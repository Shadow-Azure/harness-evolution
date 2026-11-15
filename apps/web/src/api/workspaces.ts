import type {
  Workspace,
  WorkspaceCreateRequest,
  WorkspaceCredentialCreated,
  WorkspaceCredentialListResponse,
  WorkspaceListResponse,
  WorkspaceMember,
  WorkspaceMemberCandidateListResponse,
  WorkspaceMemberCreateRequest,
  WorkspaceMemberListResponse,
  WorkspaceMemberUpdateRequest,
  WorkspaceUpdateRequest,
} from "@harness/contracts";

import { request } from "./http";

function workspacePath(workspaceId: string, suffix = ""): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}${suffix}`;
}

function memberPath(workspaceId: string, userId: string): string {
  return workspacePath(
    workspaceId,
    `/members/${encodeURIComponent(userId)}`,
  );
}

/**
 * List every workspace visible to the current session.
 *
 * Global administrators receive every workspace; other roles receive only the
 * spaces they belong to. The management page uses the same payload to render
 * both the global table and the current-space summary.
 * @returns Visible workspaces with management aggregates.
 */
export function listWorkspaces(): Promise<WorkspaceListResponse> {
  return request<WorkspaceListResponse>("/api/workspaces");
}

/**
 * Create one workspace with at least one existing initial space administrator.
 * @param body Workspace name, mark, quota, and initial administrator ids.
 * @returns The created workspace.
 */
export function createWorkspace(
  body: WorkspaceCreateRequest,
): Promise<Workspace> {
  return request<Workspace>("/api/workspaces", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Update the workspace fields permitted for the caller's effective role.
 * @param workspaceId Route workspace identifier.
 * @param body Partial workspace fields; space administrators may only change quota.
 * @returns The updated workspace.
 */
export function updateWorkspace(
  workspaceId: string,
  body: WorkspaceUpdateRequest,
): Promise<Workspace> {
  return request<Workspace>(workspacePath(workspaceId), {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/**
 * Read the member table of one workspace.
 * @param workspaceId Route workspace identifier.
 * @returns Every membership row with the joined user's public identity.
 */
export function listWorkspaceMembers(
  workspaceId: string,
): Promise<WorkspaceMemberListResponse> {
  return request<WorkspaceMemberListResponse>(
    workspacePath(workspaceId, "/members"),
  );
}

/**
 * Search users who are not members yet without exposing the global directory.
 * @param workspaceId Route workspace identifier.
 * @param query Search text; an empty query returns the first page.
 * @param limit Maximum candidates to return (1–20).
 * @returns Bounded non-member candidate page.
 */
export function listMemberCandidates(
  workspaceId: string,
  query: string,
  limit = 10,
): Promise<WorkspaceMemberCandidateListResponse> {
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  params.set("limit", String(limit));
  return request<WorkspaceMemberCandidateListResponse>(
    workspacePath(workspaceId, `/member-candidates?${params.toString()}`),
  );
}

/**
 * Add one existing user to a workspace.
 * @param workspaceId Route workspace identifier.
 * @param body Candidate user id and workspace role.
 * @returns The created membership row.
 */
export function addWorkspaceMember(
  workspaceId: string,
  body: WorkspaceMemberCreateRequest,
): Promise<WorkspaceMember> {
  return request<WorkspaceMember>(workspacePath(workspaceId, "/members"), {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Change one workspace member's role.
 * @param workspaceId Route workspace identifier.
 * @param userId Member user identifier.
 * @param body Replacement workspace role.
 * @returns The updated membership row.
 */
export function updateWorkspaceMember(
  workspaceId: string,
  userId: string,
  body: WorkspaceMemberUpdateRequest,
): Promise<WorkspaceMember> {
  return request<WorkspaceMember>(memberPath(workspaceId, userId), {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/**
 * Remove one workspace member while preserving a space administrator.
 * @param workspaceId Route workspace identifier.
 * @param userId Member user identifier.
 * @returns No value.
 */
export function removeWorkspaceMember(
  workspaceId: string,
  userId: string,
): Promise<void> {
  return request<void>(memberPath(workspaceId, userId), {
    method: "DELETE",
  });
}

/**
 * Write a real space-administrator row for the global administrator.
 * @param workspaceId Route workspace identifier.
 * @returns The idempotent space-administrator membership row.
 */
export function appointSelfAsSpaceAdmin(
  workspaceId: string,
): Promise<WorkspaceMember> {
  return request<WorkspaceMember>(
    workspacePath(workspaceId, "/members/self-admin"),
    { method: "POST" },
  );
}

/**
 * Read every ingest credential row of one workspace without plaintext.
 * @param workspaceId Route workspace identifier.
 * @returns Credential rows including revoked ones.
 */
export function listWorkspaceCredentials(
  workspaceId: string,
): Promise<WorkspaceCredentialListResponse> {
  return request<WorkspaceCredentialListResponse>(
    workspacePath(workspaceId, "/credentials"),
  );
}

/**
 * Mint one ingest credential; the plaintext is returned exactly once.
 * @param workspaceId Route workspace identifier.
 * @returns The one-time plaintext together with its prefix and id.
 */
export function createWorkspaceCredential(
  workspaceId: string,
): Promise<WorkspaceCredentialCreated> {
  return request<WorkspaceCredentialCreated>(
    workspacePath(workspaceId, "/credentials"),
    { method: "POST" },
  );
}

/**
 * Revoke one credential; already-revoked rows stay idempotent.
 * @param workspaceId Route workspace identifier.
 * @param credentialId Credential row identifier.
 * @returns No value.
 */
export function revokeWorkspaceCredential(
  workspaceId: string,
  credentialId: string,
): Promise<void> {
  return request<void>(
    workspacePath(
      workspaceId,
      `/credentials/${encodeURIComponent(credentialId)}`,
    ),
    { method: "DELETE" },
  );
}
