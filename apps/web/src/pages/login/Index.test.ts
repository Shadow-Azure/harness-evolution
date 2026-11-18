// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
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

import LoginPage from "./Index.vue";
import { createAppRouter } from "../../router";
import { server } from "../../test/server";
import { elementPlusComponents } from "../../test/setup";
import { testWorkspace } from "../../test/auth";

const ws = "/workspaces/ws-test";
const user = {
  id: "u-1",
  username: "operator",
  displayName: "操作员",
  role: "member" as const,
  mustChangePassword: false,
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  server.use(
    http.get("/api/auth/session", () =>
      HttpResponse.json({
        user,
        workspaces: [testWorkspace({ role: "viewer" })],
        truncated: false,
      }),
    ),
  );
});
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
  it("renders the V2 two-column shell with product capability copy", async () => {
    const { wrapper } = await mountPage();

    const card = wrapper.get("[data-testid='login-card']");
    expect(card.classes()).toContain("auth-card");
    const brand = wrapper.get("[data-testid='login-brand']");
    const formRegion = wrapper.get("[data-testid='login-form-region']");
    expect(brand.attributes("aria-labelledby")).toBe("login-brand-title");
    expect(formRegion.attributes("aria-labelledby")).toBe("login-form-title");
    expect(wrapper.findAll("h1")).toHaveLength(1);
    expect(wrapper.get("h1").attributes("id")).toBe("login-brand-title");

    const text = wrapper.text();
    expect(text).toContain("工作空间隔离");
    expect(text).toContain("归因进入进化流程");
    expect(text).toContain("默认 10 个 Session");
    expect(text).toContain("首次登录需要设置自己的密码");
  });

  it("does not enumerate or offer accounts", async () => {
    const { wrapper } = await mountPage();

    expect(wrapper.find("[data-testid='login-account']").exists()).toBe(false);
    expect(wrapper.text()).not.toMatch(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i);
    expect(wrapper.text()).not.toContain("演示账号");
    expect(wrapper.findAll("[data-testid^='login-account']")).toHaveLength(0);
  });

  it("keeps the form focus order after the capability region", async () => {
    const { wrapper } = await mountPage();

    const order = wrapper
      .findAll("input, button")
      .map((element) => element.attributes("name") ?? element.attributes("data-testid") ?? element.text());
    expect(order).toEqual(["username", "password", "login-submit"]);
  });

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
    await vi.waitFor(() =>
      expect(router.currentRoute.value.fullPath).toBe(
        `${ws}/sessions?sort=recent`,
      ),
    );
  });
});
