// @vitest-environment jsdom

import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { http, HttpResponse } from "msw";

import { request, resetHttpAuthHandlers } from "../api/http";
import { server } from "../test/server";
import { useAuthStore } from "../stores/auth";
import { installAuthRuntime } from "./runtime";

const user = {
  id: "u-1",
  username: "operator",
  displayName: "操作员",
  role: "member" as const,
  mustChangePassword: false,
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  resetHttpAuthHandlers();
  setActivePinia(createPinia());
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function runtimeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", component: {} },
      { path: "/change-password", component: {} },
      { path: "/sessions", component: {} },
    ],
  });
}

describe("auth runtime recovery", () => {
  it("clears stale auth and returns an expired protected request to login", async () => {
    server.use(
      http.get("/api/users", () =>
        HttpResponse.json(
          { error: { code: "AUTH_EXPIRED", message: "expired" } },
          { status: 401 },
        ),
      ),
      http.post("/api/auth/refresh", () =>
        HttpResponse.json(
          { error: { code: "AUTH_EXPIRED", message: "expired" } },
          { status: 401 },
        ),
      ),
    );
    const router = runtimeRouter();
    installAuthRuntime(router);
    const auth = useAuthStore();
    auth.setSession({ accessToken: "expired", expiresIn: 1_800, user });
    await router.push("/sessions");
    window.history.replaceState({}, "", "/sessions");

    await expect(request("/api/users")).rejects.toMatchObject({ code: "AUTH_EXPIRED" });
    await vi.waitFor(() => {
      expect(auth.user).toBeNull();
      expect(router.currentRoute.value.path).toBe("/login");
      expect(router.currentRoute.value.query.redirect).toBe("/sessions");
    });
  });

  it("marks stale forced-change state and redirects before rendering a business error", async () => {
    server.use(
      http.get("/api/users", () =>
        HttpResponse.json(
          {
            error: {
              code: "PASSWORD_CHANGE_REQUIRED",
              message: "password change required",
            },
          },
          { status: 403 },
        ),
      ),
    );
    const router = runtimeRouter();
    installAuthRuntime(router);
    const auth = useAuthStore();
    auth.setSession({ accessToken: "active", expiresIn: 1_800, user });
    await router.push("/sessions");
    window.history.replaceState({}, "", "/sessions");

    await expect(request("/api/users")).rejects.toMatchObject({
      code: "PASSWORD_CHANGE_REQUIRED",
    });
    await vi.waitFor(() => {
      expect(auth.user?.mustChangePassword).toBe(true);
      expect(router.currentRoute.value.path).toBe("/change-password");
      expect(router.currentRoute.value.query.redirect).toBe("/sessions");
    });
  });
});
