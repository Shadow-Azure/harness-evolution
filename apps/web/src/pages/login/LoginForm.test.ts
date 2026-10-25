// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { createAppRouter } from "../../router";
import { server } from "../../test/server";
import { elementPlusComponents } from "../../test/setup";
import LoginForm from "./LoginForm.vue";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

async function mountForm() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createAppRouter();
  await router.push("/login?redirect=/sessions");
  await router.isReady();
  const wrapper = mount(LoginForm, {
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

describe("login form", () => {
  it("owns validation, inline errors, and the authenticated redirect", async () => {
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
    const { router, wrapper } = await mountForm();

    await wrapper.get("form").trigger("submit");
    expect(wrapper.text()).toContain("请输入用户名和密码");

    await wrapper.get('input[name="username"]').setValue("operator");
    await wrapper.get('input[name="password"]').setValue("correct-password");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.find("[role='alert']").exists()).toBe(false);
    expect(router.currentRoute.value.fullPath).toBe("/sessions");
  });
});
