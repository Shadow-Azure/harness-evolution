// @vitest-environment jsdom

import { createPinia, setActivePinia } from "pinia";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";

import type { LoginResponse, PublicUser, RefreshResponse } from "@harness/contracts";
import { server } from "../test/server";
import { useAuthStore } from "./auth";

const initialUser: PublicUser = {
  id: "u-admin",
  username: "admin",
  displayName: "管理员",
  role: "admin",
  mustChangePassword: true,
};

const changedUser: PublicUser = {
  ...initialUser,
  mustChangePassword: false,
};

beforeEach(() => {
  setActivePinia(createPinia());
});
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("auth store", () => {
  it("stores login credentials in memory and replaces the user after refresh", async () => {
    const loginResponse: LoginResponse = {
      accessToken: "login-access",
      expiresIn: 1_800,
      user: initialUser,
    };
    const refreshResponse: RefreshResponse = {
      accessToken: "refreshed-access",
      expiresIn: 1_800,
    };
    server.use(
      http.post("/api/auth/login", () => HttpResponse.json(loginResponse)),
      http.post("/api/auth/refresh", () => HttpResponse.json(refreshResponse)),
      http.get("/api/auth/session", () =>
        HttpResponse.json({ user: changedUser, workspaces: [], truncated: false }),
      ),
    );
    const store = useAuthStore();

    await expect(
      store.login({ username: "admin", password: "temporary-password" }),
    ).resolves.toEqual(initialUser);
    expect(store.accessToken).toBe("login-access");
    expect(store.user).toEqual(changedUser);
    expect(store.isAuthenticated).toBe(true);

    await expect(store.refresh()).resolves.toBe(true);
    expect(store.accessToken).toBe("refreshed-access");
    await expect(store.loadCurrentUser()).resolves.toEqual(changedUser);
    expect(store.user).toEqual(changedUser);
  });

  it("keeps visible workspaces from auth/session and clears them on logout", async () => {
    const workspaces = [
      {
        id: "ws-a",
        name: "空间 A",
        mark: "A",
        role: "space_admin" as const,
        quota: 60,
        used: 3,
        memberCount: 2,
        spaceAdminCount: 1,
      },
    ];
    server.use(
      http.post("/api/auth/refresh", () =>
        HttpResponse.json({ accessToken: "restored", expiresIn: 1_800 }),
      ),
      http.get("/api/auth/session", () =>
        HttpResponse.json({ user: changedUser, workspaces, truncated: false }),
      ),
      http.post("/api/auth/logout", () => new HttpResponse(null, { status: 204 })),
    );
    const store = useAuthStore();

    await expect(store.tryRefresh()).resolves.toBe(true);
    expect(store.workspaces).toEqual(workspaces);
    expect(store.workspaceById("ws-a")?.role).toBe("space_admin");
    expect(store.workspaceById("ws-missing")).toBeNull();

    await store.logout({ clear: vi.fn() });
    expect(store.workspaces).toEqual([]);
    expect(store.sessionTruncated).toBe(false);
  });

  it("clears a half-authenticated login when auth/session fails", async () => {
    server.use(
      http.post("/api/auth/login", () =>
        HttpResponse.json({
          accessToken: "access-token",
          expiresIn: 1_800,
          user: initialUser,
        }),
      ),
      http.get("/api/auth/session", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL", message: "failed" } },
          { status: 500 },
        ),
      ),
    );
    const store = useAuthStore();

    await expect(
      store.login({ username: "admin", password: "temporary-password" }),
    ).rejects.toMatchObject({ status: 500 });
    expect(store.isAuthenticated).toBe(false);
    expect(store.user).toBeNull();
    expect(store.accessToken).toBeNull();
    expect(store.isBootstrapped).toBe(true);
  });

  it("clears stale state when refresh has no valid cookie", async () => {
    server.use(
      http.post("/api/auth/refresh", () =>
        HttpResponse.json(
          { error: { code: "AUTH_EXPIRED", message: "expired" } },
          { status: 401 },
        ),
      ),
    );
    const store = useAuthStore();
    store.accessToken = "stale";
    store.user = initialUser;
    store.isBootstrapped = false;

    await expect(store.tryRefresh()).resolves.toBe(false);
    expect(store.accessToken).toBeNull();
    expect(store.user).toBeNull();
    expect(store.isBootstrapped).toBe(true);
  });

  it("restores the current user from the refresh cookie exactly once", async () => {
    let refreshCalls = 0;
    server.use(
      http.post("/api/auth/refresh", () => {
        refreshCalls += 1;
        return HttpResponse.json({ accessToken: "restored-access", expiresIn: 1_800 });
      }),
      http.get("/api/auth/session", () =>
        HttpResponse.json({ user: changedUser, workspaces: [], truncated: false }),
      ),
    );
    const store = useAuthStore();

    await expect(Promise.all([store.tryRefresh(), store.tryRefresh()])).resolves.toEqual([
      true,
      true,
    ]);
    expect(refreshCalls).toBe(1);
    expect(store.accessToken).toBe("restored-access");
    expect(store.user).toEqual(changedUser);
  });

  it("checks the refreshed user before completing a forced password change", async () => {
    const calls: string[] = [];
    server.use(
      http.post("/api/auth/change-password", () => {
        calls.push("change");
        return new HttpResponse(null, { status: 204 });
      }),
      http.post("/api/auth/refresh", () => {
        calls.push("refresh");
        return HttpResponse.json({ accessToken: "new-access", expiresIn: 1_800 });
      }),
      http.get("/api/auth/session", () => {
        calls.push("session");
        return HttpResponse.json({
          user: changedUser,
          workspaces: [],
          truncated: false,
        });
      }),
    );
    const store = useAuthStore();
    store.setSession({ accessToken: "old-access", expiresIn: 1_800, user: initialUser });

    await store.changePassword({
      oldPassword: "temporary-password",
      newPassword: "replacement-password",
    });

    expect(calls).toEqual(["change", "refresh", "session"]);
    expect(store.user).toEqual(changedUser);
    expect(store.user?.mustChangePassword).toBe(false);
  });

  it("clears the query cache on logout even if the API request fails", async () => {
    const clear = vi.fn();
    server.use(
      http.post("/api/auth/logout", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL", message: "temporary failure" } },
          { status: 500 },
        ),
      ),
    );
    const store = useAuthStore();
    store.setSession({ accessToken: "active", expiresIn: 1_800, user: changedUser });

    await store.logout({ clear });

    expect(clear).toHaveBeenCalledOnce();
    expect(store.accessToken).toBeNull();
    expect(store.user).toBeNull();
  });
});
