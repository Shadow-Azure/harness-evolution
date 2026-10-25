// @vitest-environment jsdom

import type { PublicUser } from "@harness/contracts";
import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent } from "vue";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { createAppRouter } from "../router";
import { useAuthStore } from "../stores/auth";
import { server } from "../test/server";
import {
  useChangePassword,
  useCurrentUser,
  useLogin,
  useLogout,
} from "./useAuth";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

type AuthComposables = {
  login: ReturnType<typeof useLogin>;
  logout: ReturnType<typeof useLogout>;
  currentUser: ReturnType<typeof useCurrentUser>;
  changePassword: ReturnType<typeof useChangePassword>;
};

async function mountComposables(initialPath = "/login", user: PublicUser | null = null) {
  const pinia = createPinia();
  setActivePinia(pinia);
  if (user) {
    useAuthStore(pinia).setSession({
      accessToken: "active",
      expiresIn: 1_800,
      user,
    });
  }
  const queryClient = new QueryClient();
  const router = createAppRouter();
  await router.push(initialPath);
  await router.isReady();
  let composables!: AuthComposables;
  const Harness = defineComponent({
    setup() {
      composables = {
        login: useLogin(),
        logout: useLogout(),
        currentUser: useCurrentUser(),
        changePassword: useChangePassword(),
      };
      return () => null;
    },
  });
  const wrapper = mount(Harness, {
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient }],
        pinia,
        router,
      ],
    },
  });
  return { composables, pinia, queryClient, router, wrapper };
}

describe("auth composables", () => {
  it("expose the shared request-state contract", async () => {
    const { composables, wrapper } = await mountComposables();
    const expectedKeys = ["data", "isLoading", "isError", "error", "refetch"];

    for (const state of Object.values(composables)) {
      expect(Object.keys(state)).toEqual(expect.arrayContaining(expectedKeys));
    }
    wrapper.unmount();
  });

  it("refetch updates mutation data and restores current user state", async () => {
    server.use(
      http.post("/api/auth/login", () =>
        HttpResponse.json({
          accessToken: "access-token",
          expiresIn: 1_800,
          user: {
            id: "u-1",
            username: "operator",
            displayName: "操作员",
            role: "member",
            mustChangePassword: false,
          },
        }),
      ),
    );
    const { composables, pinia, router, wrapper } = await mountComposables();

    await composables.login.refetch({
      username: "operator",
      password: "correct-password",
    });
    await flushPromises();

    expect(composables.login.data.value?.displayName).toBe("操作员");
    expect(useAuthStore(pinia).user?.displayName).toBe("操作员");
    expect(composables.currentUser.data.value?.displayName).toBe("操作员");
    expect(router.currentRoute.value.path).toBe("/sessions");
    wrapper.unmount();
  });

  it("returns to login when refresh fails after changing the password", async () => {
    server.use(
      http.post(
        "/api/auth/change-password",
        () => new HttpResponse(null, { status: 204 }),
      ),
      http.post("/api/auth/refresh", () =>
        HttpResponse.json(
          { error: { code: "AUTH_EXPIRED", message: "expired" } },
          { status: 401 },
        ),
      ),
    );
    const user: PublicUser = {
      id: "u-1",
      username: "operator",
      displayName: "操作员",
      role: "member",
      mustChangePassword: true,
    };
    const { composables, pinia, queryClient, router, wrapper } = await mountComposables(
      "/change-password?redirect=/sessions",
      user,
    );
    const auth = useAuthStore(pinia);
    queryClient.setQueryData(["sessions"], [{ id: "s-1" }]);

    await expect(
      composables.changePassword.refetch({
        oldPassword: "temporary-password",
        newPassword: "replacement-password",
      }),
    ).rejects.toBeTruthy();
    await flushPromises();

    expect(auth.isAuthenticated).toBe(false);
    expect(queryClient.getQueryData(["sessions"])).toBeUndefined();
    expect(router.currentRoute.value.path).toBe("/login");
    expect(router.currentRoute.value.query.redirect).toBe("/sessions");
    wrapper.unmount();
  });

  it("tracks current-user refetch failures and clears them after recovery", async () => {
    let calls = 0;
    server.use(
      http.get("/api/auth/me", () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              { error: { code: "INTERNAL", message: "temporary failure" } },
              { status: 500 },
            )
          : HttpResponse.json({
              id: "u-1",
              username: "operator",
              displayName: "操作员",
              role: "member",
              mustChangePassword: false,
            });
      }),
    );
    const { composables, pinia, wrapper } = await mountComposables("/sessions");
    const auth = useAuthStore(pinia);
    auth.setSession({
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

    await expect(composables.currentUser.refetch()).rejects.toMatchObject({
      code: "INTERNAL",
    });
    expect(composables.currentUser.isLoading.value).toBe(false);
    expect(composables.currentUser.isError.value).toBe(true);
    expect(composables.currentUser.error.value).toMatchObject({ code: "INTERNAL" });

    await expect(composables.currentUser.refetch()).resolves.toMatchObject({ id: "u-1" });
    expect(composables.currentUser.isError.value).toBe(false);
    expect(composables.currentUser.error.value).toBeNull();
    wrapper.unmount();
  });
});
