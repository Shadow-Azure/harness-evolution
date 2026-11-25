/**
 * Workspace and auth/session contracts from the V2 design.
 *
 * Every payload type is generated from the FastAPI OpenAPI snapshot; this
 * module only re-exports them under stable names and keeps the role unions.
 */

import type { components } from "./generated/api.js";

/** Effective role of the current user inside one workspace. */
export type WorkspaceRole = "global_admin" | "space_admin" | "member" | "viewer";

/** Role stored on a workspace membership row; global admins are never stored. */
export type WorkspaceMemberRole = Exclude<WorkspaceRole, "global_admin">;

/** Minimal identity of one workspace administrator shown on a workspace card. */
export type WorkspaceAdmin = components["schemas"]["WorkspaceAdmin"];

/** Full workspace returned by the management API. */
export type Workspace = components["schemas"]["Workspace"];

/** Workspace summary embedded in the auth/session payload. */
export type SessionWorkspace = components["schemas"]["SessionWorkspace"];

/** One workspace list response. */
export type WorkspaceListResponse = components["schemas"]["WorkspaceListResponse"];

/** Administrator-provisioned workspace body. */
export type WorkspaceCreateRequest = components["schemas"]["WorkspaceCreateRequest"];

/** Partial workspace update body. */
export type WorkspaceUpdateRequest = components["schemas"]["WorkspaceUpdateRequest"];

/** One membership row returned by the workspace member endpoints. */
export type WorkspaceMember = components["schemas"]["WorkspaceMember"];

/** One workspace member list response. */
export type WorkspaceMemberListResponse =
  components["schemas"]["WorkspaceMemberListResponse"];

/** One non-member user returned by the candidate search. */
export type WorkspaceMemberCandidate = components["schemas"]["WorkspaceMemberCandidate"];

/** One bounded candidate list response. */
export type WorkspaceMemberCandidateListResponse =
  components["schemas"]["WorkspaceMemberCandidateListResponse"];

/** Add-one-member body. */
export type WorkspaceMemberCreateRequest =
  components["schemas"]["WorkspaceMemberCreateRequest"];

/** Change-one-role body. */
export type WorkspaceMemberUpdateRequest =
  components["schemas"]["WorkspaceMemberUpdateRequest"];

/** One ingest credential without its one-time plaintext secret. */
export type WorkspaceCredential = components["schemas"]["WorkspaceCredential"];

/** One credential list response. */
export type WorkspaceCredentialListResponse =
  components["schemas"]["WorkspaceCredentialListResponse"];

/** One-time credential creation response; `credential` is never persisted. */
export type WorkspaceCredentialCreated = components["schemas"]["WorkspaceCredentialCreated"];

/** One label rule set plus its current distinct assignment count. */
export type WorkspaceBadCaseLabelConfiguration =
  components["schemas"]["WorkspaceBadCaseLabelConfiguration"];

/** Complete replacement set for one workspace's accepted public labels. */
export type WorkspaceBadCaseLabelRequest =
  components["schemas"]["WorkspaceBadCaseLabelRequest"];

/** Current user plus every workspace they can see for this session. */
export type SessionPayload = components["schemas"]["SessionPayload"];
