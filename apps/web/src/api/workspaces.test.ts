// @vitest-environment jsdom

import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { server } from "../test/server";
import {
  addWorkspaceMember,
  appointSelfAsSpaceAdmin,
  createWorkspace,
  createWorkspaceCredential,
  listMemberCandidates,
  listWorkspaceCredentials,
  listWorkspaceMembers,
  listWorkspaces,
  removeWorkspaceMember,
  revokeWorkspaceCredential,
  updateWorkspace,
  updateWorkspaceMember,
} from "./workspaces";
import { listUsers } from "./users";

const workspaceId = "ws-test";
const base = `/api/workspaces/${workspaceId}`;

const workspace = {
  id: workspaceId,
  name: "测试空间",
  mark: "WT",
  quota: 60,
  used: 12,
  memberCount: 2,
  spaceAdmins: [{ id: "u-admin", displayName: "管理员" }],
  knowledgeRoots: [],
  createdAt: "2026-11-01T10:00:00+08:00",
};

const member = {
  workspaceId,
  userId: "u-member",
  username: "member",
  displayName: "成员甲",
  role: "member" as const,
  joinedAt: "2026-11-02T10:01:00+08:00",
  updatedAt: "2026-11-02T10:01:00+08:00",
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("workspace admin API", () => {
  it("lists visible workspaces and the administrator user directory", async () => {
    server.use(
      http.get("/api/workspaces", () =>
        HttpResponse.json({ items: [workspace] }),
      ),
      http.get("/api/users", () =>
        HttpResponse.json({
          items: [
            {
              id: "u-admin",
              username: "admin",
              displayName: "管理员",
              role: "admin",
              mustChangePassword: false,
            },
          ],
        }),
      ),
    );

    await expect(listWorkspaces()).resolves.toEqual({ items: [workspace] });
    await expect(listUsers()).resolves.toMatchObject({
      items: [{ id: "u-admin", role: "admin" }],
    });
  });

  it("creates a workspace with the documented camelCase body", async () => {
    let received: unknown;
    server.use(
      http.post("/api/workspaces", async ({ request }) => {
        received = await request.json();
        expect(request.headers.get("content-type")).toContain(
          "application/json",
        );
        return HttpResponse.json(workspace, { status: 201 });
      }),
    );
    const body = {
      name: "测试空间",
      mark: "WT",
      quota: 60,
      spaceAdminIds: ["u-admin"],
    };

    await expect(createWorkspace(body)).resolves.toEqual(workspace);
    expect(received).toEqual(body);
  });

  it("updates only the quota field through the workspace path", async () => {
    let received: unknown;
    server.use(
      http.put(`${base}`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ ...workspace, quota: 80 });
      }),
    );

    await expect(updateWorkspace(workspaceId, { quota: 80 })).resolves.toMatchObject(
      { quota: 80 },
    );
    expect(received).toEqual({ quota: 80 });
  });

  it("reads members and searches non-member candidates with encoded query", async () => {
    const seen: string[] = [];
    server.use(
      http.get(`${base}/members`, () =>
        HttpResponse.json({ items: [member] }),
      ),
      http.get(`${base}/member-candidates`, ({ request }) => {
        const url = new URL(request.url);
        seen.push(`${url.searchParams.get("q")}|${url.searchParams.get("limit")}`);
        return HttpResponse.json({
          items: [
            {
              id: "u-candidate",
              username: "candidate",
              displayName: "候选乙",
              active: true,
            },
          ],
        });
      }),
    );

    await expect(listWorkspaceMembers(workspaceId)).resolves.toEqual({
      items: [member],
    });
    await expect(
      listMemberCandidates(workspaceId, "候选 乙", 5),
    ).resolves.toMatchObject({
      items: [{ id: "u-candidate" }],
    });
    expect(seen).toEqual(["候选 乙|5"]);
  });

  it("adds, updates, and removes members through the member routes", async () => {
    const calls: string[] = [];
    let createBody: unknown;
    let updateBody: unknown;
    server.use(
      http.post(`${base}/members`, async ({ request }) => {
        calls.push("POST members");
        createBody = await request.json();
        return HttpResponse.json(member, { status: 201 });
      }),
      http.put(`${base}/members/u-member`, async ({ request }) => {
        calls.push("PUT member");
        updateBody = await request.json();
        return HttpResponse.json({ ...member, role: "viewer" });
      }),
      http.delete(
        `${base}/members/u-member`,
        () => new HttpResponse(null, { status: 204 }),
      ),
      http.post(`${base}/members/self-admin`, () => {
        calls.push("POST self-admin");
        return HttpResponse.json(member);
      }),
    );

    await expect(
      addWorkspaceMember(workspaceId, {
        userId: "u-member",
        role: "member",
      }),
    ).resolves.toEqual(member);
    expect(createBody).toEqual({ userId: "u-member", role: "member" });
    await expect(
      updateWorkspaceMember(workspaceId, "u-member", { role: "viewer" }),
    ).resolves.toMatchObject({ role: "viewer" });
    expect(updateBody).toEqual({ role: "viewer" });
    await expect(
      removeWorkspaceMember(workspaceId, "u-member"),
    ).resolves.toBeUndefined();
    await expect(appointSelfAsSpaceAdmin(workspaceId)).resolves.toEqual(member);
    expect(calls).toEqual([
      "POST members",
      "PUT member",
      "POST self-admin",
    ]);
  });

  it("lists, creates, and revokes credentials with encoded ids", async () => {
    const seen: string[] = [];
    server.use(
      http.get(`${base}/credentials`, () =>
        HttpResponse.json({ items: [] }),
      ),
      http.post(`${base}/credentials`, () => {
        seen.push("POST credentials");
        return HttpResponse.json(
          {
            credentialId: "cred-1",
            prefix: "whk_123",
            credential: "whk_123_secret",
          },
          { status: 201 },
        );
      }),
      http.delete(`${base}/credentials/cred%2F1`, ({ request }) => {
        seen.push(new URL(request.url).pathname);
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await expect(listWorkspaceCredentials(workspaceId)).resolves.toEqual({
      items: [],
    });
    await expect(createWorkspaceCredential(workspaceId)).resolves.toMatchObject({
      credentialId: "cred-1",
      prefix: "whk_123",
    });
    await expect(
      revokeWorkspaceCredential(workspaceId, "cred/1"),
    ).resolves.toBeUndefined();
    expect(seen).toEqual([
      "POST credentials",
      `${base}/credentials/cred%2F1`,
    ]);
  });
});
