// @vitest-environment jsdom

import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "../stores/auth";
import { server } from "../test/server";
import { createAppRouter } from "./index";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => setActivePinia(createPinia()));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function refreshHandlers(mustChangePassword: boolean) {
  return [
    http.post("/api/auth/refresh", () =>
      HttpResponse.json({ accessToken: "restored", expiresIn: 1_800 }),
    ),
    http.get("/api/auth/me", () =>
      HttpResponse.json({
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword,
      }),
    ),
  ];
}

describe("MSW-driven auth guard branches", () => {
  it("restores a normal user before resolving a protected deep link", async () => {
    server.use(...refreshHandlers(false));
    const router = createAppRouter();

    await router.push("/sessions?sort=recent");
    await router.isReady();

    expect(router.currentRoute.value.fullPath).toBe("/sessions?sort=recent");
    expect(useAuthStore().accessToken).toBe("restored");
  });

  it("restores a first-login user and redirects to password change", async () => {
    server.use(...refreshHandlers(true));
    const router = createAppRouter();

    await router.push("/sessions?sort=recent");
    await router.isReady();

    expect(router.currentRoute.value.path).toBe("/change-password");
    expect(router.currentRoute.value.query.redirect).toBe("/sessions?sort=recent");
  });

  it("rejects an external redirect target for an authenticated login visit", async () => {
    const store = useAuthStore();
    store.setSession({
      accessToken: "active",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();

    await router.push("/login?redirect=//evil.example");
    await router.isReady();

    expect(router.currentRoute.value.fullPath).toBe("/sessions");
  });
});
