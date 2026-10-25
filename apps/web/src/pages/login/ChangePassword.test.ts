// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { useAuthStore } from "../../stores/auth";
import { server } from "../../test/server";
import { elementPlusComponents } from "../../test/setup";
import { createAppRouter } from "../../router";
import ChangePasswordPage from "./ChangePassword.vue";

const firstLoginUser = {
  id: "u-1",
  username: "operator",
  displayName: "操作员",
  role: "member" as const,
  mustChangePassword: true,
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

async function mountPage() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const store = useAuthStore();
  store.setSession({ accessToken: "access", expiresIn: 1_800, user: firstLoginUser });
  const router = createAppRouter();
  await router.push("/change-password?redirect=/sessions");
  await router.isReady();
  const wrapper = mount(ChangePasswordPage, {
    global: {
      components: elementPlusComponents,
      plugins: [
        [VueQueryPlugin, { queryClient: new QueryClient() }],
        pinia,
        router,
      ],
    },
  });
  return { router, store, wrapper };
}

describe("change-password page", () => {
  it("rejects mismatched and unchanged replacement passwords before HTTP", async () => {
    const { wrapper } = await mountPage();

    await wrapper.get('input[name="oldPassword"]').setValue("temporary-password");
    await wrapper.get('input[name="newPassword"]').setValue("replacement-password");
    await wrapper.get('input[name="confirmPassword"]').setValue("different-password");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("两次输入的新密码不一致");

    await wrapper.get('input[name="newPassword"]').setValue("temporary-password");
    await wrapper.get('input[name="confirmPassword"]').setValue("temporary-password");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("新密码不能与当前密码相同");
  });

  it("refreshes identity after the change and follows the validated redirect", async () => {
    server.use(
      http.post("/api/auth/change-password", () => new HttpResponse(null, { status: 204 })),
      http.post("/api/auth/refresh", () =>
        HttpResponse.json({ accessToken: "new-access", expiresIn: 1_800 }),
      ),
      http.get("/api/auth/me", () =>
        HttpResponse.json({ ...firstLoginUser, mustChangePassword: false }),
      ),
    );
    const { router, store, wrapper } = await mountPage();

    await wrapper.get('input[name="oldPassword"]').setValue("temporary-password");
    await wrapper.get('input[name="newPassword"]').setValue("replacement-password");
    await wrapper.get('input[name="confirmPassword"]').setValue("replacement-password");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(store.accessToken).toBe("new-access");
    expect(store.user?.mustChangePassword).toBe(false);
    expect(router.currentRoute.value.fullPath).toBe("/sessions");
  });
});
