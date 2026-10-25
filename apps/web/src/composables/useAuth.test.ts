// @vitest-environment jsdom

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

async function mountComposables() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const queryClient = new QueryClient();
  const router = createAppRouter();
  await router.push("/login");
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
  return { composables, pinia, router, wrapper };
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
});
