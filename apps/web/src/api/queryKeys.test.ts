import { QueryClient } from "@tanstack/vue-query";
import { describe, expect, it } from "vitest";

import { queryKeys } from "./queryKeys";

describe("workspace query keys", () => {
  it("prefixes every workspace-owned resource with [ws, wid]", () => {
    const workspaceId = "ws-a";
    expect(queryKeys.sessions(workspaceId)).toEqual(["ws", workspaceId, "sessions"]);
    expect(queryKeys.sessionList(workspaceId, { q: "x" })).toEqual([
      "ws",
      workspaceId,
      "sessions",
      { q: "x" },
    ]);
    expect(queryKeys.session(workspaceId, "s-1")).toEqual([
      "ws",
      workspaceId,
      "session",
      "s-1",
    ]);
    expect(queryKeys.sessionTree(workspaceId, "s-1")).toEqual([
      "ws",
      workspaceId,
      "session",
      "s-1",
      "tree",
    ]);
    expect(queryKeys.sessionBadCases(workspaceId, "s-1")).toEqual([
      "ws",
      workspaceId,
      "session",
      "s-1",
      "bad-cases",
    ]);
    expect(queryKeys.badCase(workspaceId, "case-1")).toEqual([
      "ws",
      workspaceId,
      "case",
      "case-1",
      "detail",
      "unscoped",
    ]);
    expect(queryKeys.evolutionRuns(workspaceId)).toEqual([
      "ws",
      workspaceId,
      "evolution",
      "runs",
    ]);
    expect(queryKeys.evolutionTargets(workspaceId)).toEqual([
      "ws",
      workspaceId,
      "evolution",
      "targets",
    ]);
    expect(queryKeys.catalogs(workspaceId)).toEqual([
      "ws",
      workspaceId,
      "catalogs",
    ]);
    expect(queryKeys.overview(workspaceId)).toEqual([
      "ws",
      workspaceId,
      "overview",
    ]);
    expect(
      queryKeys.overviewSummary(workspaceId, { range: 30, objects: ["a"] }),
    ).toEqual([
      "ws",
      workspaceId,
      "overview",
      "summary",
      { range: 30, objects: ["a"] },
    ]);
    expect(
      queryKeys.overviewTrend(workspaceId, { range: 30, grain: "week" }),
    ).toEqual([
      "ws",
      workspaceId,
      "overview",
      "trend",
      { range: 30, grain: "week" },
    ]);
    expect(
      queryKeys.overviewSources(workspaceId, { objects: [] }),
    ).toEqual(["ws", workspaceId, "overview", "sources", { objects: [] }]);
    expect(
      queryKeys.overviewCases(workspaceId, { page: 2, pageSize: 8 }),
    ).toEqual([
      "ws",
      workspaceId,
      "overview",
      "cases",
      { page: 2, pageSize: 8 },
    ]);
    expect(queryKeys.adminMembers(workspaceId)).toEqual([
      "ws",
      workspaceId,
      "admin",
      "members",
    ]);
    expect(queryKeys.adminMemberCandidates(workspaceId, "q")).toEqual([
      "ws",
      workspaceId,
      "admin",
      "member-candidates",
      "q",
    ]);
    expect(queryKeys.adminCredentials(workspaceId)).toEqual([
      "ws",
      workspaceId,
      "admin",
      "credentials",
    ]);
    expect(queryKeys.workspaces()).toEqual(["ws"]);
    expect(queryKeys.users()).toEqual(["users"]);
  });

  it("keeps two workspaces in separate cache branches", () => {
    const client = new QueryClient();
    client.setQueryData(queryKeys.sessionList("ws-a", {}), [{ id: "a" }]);
    client.setQueryData(queryKeys.sessionList("ws-b", {}), [{ id: "b" }]);

    expect(client.getQueryData(queryKeys.sessionList("ws-a", {}))).toEqual([
      { id: "a" },
    ]);
    expect(client.getQueryData(queryKeys.sessionList("ws-b", {}))).toEqual([
      { id: "b" },
    ]);
  });

  it("invalidates only the switched workspace prefix", async () => {
    const client = new QueryClient();
    client.setQueryData(queryKeys.sessionList("ws-a", {}), [{ id: "a" }]);
    client.setQueryData(queryKeys.sessionList("ws-b", {}), [{ id: "b" }]);

    await client.invalidateQueries({ queryKey: queryKeys.workspace("ws-a") });

    expect(
      client.getQueryState(queryKeys.sessionList("ws-a", {}))?.isInvalidated,
    ).toBe(true);
    expect(
      client.getQueryState(queryKeys.sessionList("ws-b", {}))?.isInvalidated,
    ).toBe(false);
  });

  it("does not leak the legacy global session key", () => {
    expect(queryKeys.sessionList("ws-a", {})[0]).toBe("ws");
    expect(queryKeys.sessionList("ws-a", {})[0]).not.toBe("sessions");
  });
});
