import { describe, expect, it } from "vitest";

import {
  defaultLandingPath,
  forgetLastWorkspace,
  isLegacyWorkspacePath,
  legacyWorkspaceTarget,
  readLastWorkspaceId,
  rememberWorkspace,
  resolveLegacyWorkspace,
  switchableWorkspaceChild,
  workspacePath,
} from "./workspace";

describe("workspace route helpers", () => {
  it("builds workspace paths and strips leading child slashes", () => {
    expect(workspacePath("ws-1")).toBe("/workspaces/ws-1");
    expect(workspacePath("ws 1", "/sessions")).toBe(
      "/workspaces/ws%201/sessions",
    );
    expect(workspacePath("ws-1", "evolution/runs/r-1")).toBe(
      "/workspaces/ws-1/evolution/runs/r-1",
    );
  });

  it("recognizes legacy workspace-less paths only", () => {
    expect(isLegacyWorkspacePath("/")).toBe(true);
    expect(isLegacyWorkspacePath("/errors")).toBe(true);
    expect(isLegacyWorkspacePath("/sessions")).toBe(true);
    expect(isLegacyWorkspacePath("/sessions/s-1/errors")).toBe(true);
    expect(isLegacyWorkspacePath("/evolution/targets")).toBe(true);
    expect(isLegacyWorkspacePath("/workspaces/ws-1/sessions")).toBe(false);
    expect(isLegacyWorkspacePath("/workspaces")).toBe(false);
    expect(isLegacyWorkspacePath("/login")).toBe(false);
  });

  it("maps legacy paths without changing their suffix", () => {
    expect(legacyWorkspaceTarget("ws-1", "/")).toBe(
      "/workspaces/ws-1/overview",
    );
    expect(legacyWorkspaceTarget("ws-1", "/sessions")).toBe(
      "/workspaces/ws-1/sessions",
    );
    expect(legacyWorkspaceTarget("ws-1", "/errors")).toBe(
      "/workspaces/ws-1/sessions",
    );
    expect(legacyWorkspaceTarget("ws-1", "/sessions/s-1")).toBe(
      "/workspaces/ws-1/sessions/s-1",
    );
    expect(legacyWorkspaceTarget("ws-1", "/evolution/targets")).toBe(
      "/workspaces/ws-1/evolution/targets",
    );
  });

  it("drops workspace-scoped resource ids when switching spaces", () => {
    expect(switchableWorkspaceChild("/sessions")).toBe("/sessions");
    expect(switchableWorkspaceChild("/sessions/s-1")).toBe("/sessions");
    expect(switchableWorkspaceChild("/sessions/s-1/errors")).toBe(
      "/sessions",
    );
    expect(switchableWorkspaceChild("/evolution")).toBe("/evolution");
    expect(switchableWorkspaceChild("/evolution/targets")).toBe(
      "/evolution/targets",
    );
    expect(switchableWorkspaceChild("/evolution/runs/r-1")).toBe(
      "/evolution",
    );
    expect(switchableWorkspaceChild("/evolution/cluster/r-1")).toBe(
      "/evolution",
    );
  });

  it("resolves the remembered workspace only while still visible", () => {
    expect(
      resolveLegacyWorkspace("ws-a", [{ id: "ws-a" }, { id: "ws-b" }]),
    ).toBe("ws-a");
    expect(
      resolveLegacyWorkspace("ws-gone", [{ id: "ws-a" }, { id: "ws-b" }]),
    ).toBeNull();
    expect(resolveLegacyWorkspace(null, [{ id: "ws-only" }])).toBe("ws-only");
    expect(resolveLegacyWorkspace(null, [])).toBeNull();
  });

  it("sends a landing path to the remembered workspace or the chooser", () => {
    expect(
      defaultLandingPath({ workspaces: [{ id: "ws-only" }] }),
    ).toBe("/workspaces/ws-only/overview");
    expect(
      defaultLandingPath({
        workspaces: [{ id: "ws-a" }, { id: "ws-b" }],
      }),
    ).toBe("/workspaces");
  });

  it("round-trips the remembered workspace through storage", () => {
    const values = new Map<string, string>();
    const previous = globalThis.localStorage;
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => values.get(key) ?? null,
        setItem: (key: string, value: string) => values.set(key, value),
        removeItem: (key: string) => values.delete(key),
      },
    });
    try {
      expect(readLastWorkspaceId()).toBeNull();
      rememberWorkspace("ws-a");
      expect(readLastWorkspaceId()).toBe("ws-a");
      forgetLastWorkspace();
      expect(readLastWorkspaceId()).toBeNull();
    } finally {
      Object.defineProperty(globalThis, "localStorage", {
        configurable: true,
        value: previous,
      });
    }
  });
});
