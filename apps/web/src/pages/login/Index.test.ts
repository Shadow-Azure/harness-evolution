// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import LoginPage from "./Index.vue";
import { createAppRouter } from "../../router";
import { server } from "../../test/server";
import { elementPlusComponents } from "../../test/setup";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

async function mountPage(path = "/login?redirect=/sessions") {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createAppRouter();
  await router.push(path);
  await router.isReady();
  const wrapper = mount(LoginPage, {
    global: {
      components: elementPlusComponents,
      plugins: [
        [VueQueryPlugin, { queryClient: new QueryClient() }],
        pinia,
        router,
      ],
    },
  });
  return { router, wrapper };
}

describe("login page", () => {
  it("shows an accessible inline message for invalid credentials", async () => {
    server.use(
      http.post("/api/auth/login", () =>
        HttpResponse.json(
          { error: { code: "AUTH_INVALID", message: "invalid credentials" } },
          { status: 401 },
        ),
      ),
    );
    const { wrapper } = await mountPage();

    await wrapper.get('input[name="username"]').setValue("admin");
    await wrapper.get('input[name="password"]').setValue("wrong-password");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("用户名或密码错误");
    expect(wrapper.get("[role='alert']").attributes("aria-live")).toBe("polite");
    expect(wrapper.find("button.alert").exists()).toBe(false);
  });

  it("stores a successful session and follows the validated redirect", async () => {
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
    const { router, wrapper } = await mountPage("/login?redirect=/sessions?sort=recent");

    await wrapper.get('input[name="username"]').setValue("operator");
    await wrapper.get('input[name="password"]').setValue("correct-password");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/sessions?sort=recent");
  });
});
