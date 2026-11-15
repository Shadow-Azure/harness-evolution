/**
 * Workspace and auth/session contracts from the V2 design.
 *
 * `SessionPayload` and `SessionWorkspace` are generated from the FastAPI
 * OpenAPI snapshot after m7-03. The remaining management types stay explicit
 * until their endpoints land; field names mirror `plans/fullstack-design/05-api-design.md`
 * §3.7 so the generated types can replace them without a UI rewrite.
 */

import type { components } from "./generated/api.js";

/** Effective role of the current user inside one workspace. */
export type WorkspaceRole = "global_admin" | "space_admin" | "member" | "viewer";

/** Role stored on a workspace membership row; global admins are never stored. */
export type WorkspaceMemberRole = Exclude<WorkspaceRole, "global_admin">;

/** Minimal identity of one workspace administrator shown on a workspace card. */
export interface WorkspaceAdmin {
  id: string;
  displayName: string;
}

/** Full workspace returned by the management API. */
export interface Workspace {
  id: string;
  name: string;
  mark: string;
  quota: number;
  used: number;
  memberCount: number;
  spaceAdmins: WorkspaceAdmin[];
  createdAt: string;
}

/** Workspace summary embedded in the auth/session payload. */
export type SessionWorkspace = components["schemas"]["SessionWorkspace"];

/** One membership row returned by the workspace member endpoints. */
export interface WorkspaceMember {
  workspaceId: string;
  userId: string;
  username: string;
  displayName: string;
  role: WorkspaceMemberRole;
  joinedAt: string;
  updatedAt: string;
}

/** One ingest credential without its one-time plaintext secret. */
export interface WorkspaceCredential {
  id: string;
  prefix: string;
  createdAt: string;
  lastUsedAt: string | null;
  revokedAt: string | null;
}

/** One-time credential creation response; `credential` is never persisted. */
export interface WorkspaceCredentialCreated {
  credentialId: string;
  prefix: string;
  credential: string;
}

/** Current user plus every workspace they can see for this session. */
export type SessionPayload = components["schemas"]["SessionPayload"];
