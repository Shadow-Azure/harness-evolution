// @vitest-environment jsdom

import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import type { EvolutionTarget } from "@harness/contracts";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { createAppRouter } from "../../../router";
import { useAuthStore } from "../../../stores/auth";
import { server } from "../../../test/server";
import TargetConfigPage from "./Index.vue";

const wrappers: VueWrapper[] = [];

const target: EvolutionTarget = {
  id: "target-1",
  objectType: "skill",
  objectName: "deep-research",
  repoUrl: "https://example.com/skills.git",
  subDir: "skills/deep-research",
  defaultRef: "main",
  enabled: true,
};

async function mountPage(role: "admin" | "member") {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().setSession({
    accessToken: "access",
    expiresIn: 1_800,
    user: {
      id: "user-1",
      username: role,
      displayName: role,
      role,
      mustChangePassword: false,
    },
  });
  const router = createAppRouter();
  await router.push("/evolution/targets");
  await router.isReady();
  const wrapper = mount(TargetConfigPage, {
    global: {
      plugins: [
        [
          VueQueryPlugin,
          {
            queryClient: new QueryClient({
              defaultOptions: { queries: { gcTime: 0, retry: false } },
            }),
          },
        ],
        pinia,
        router,
      ],
    },
  });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
});
afterAll(() => server.close());

describe("target configuration page", () => {
  it("renders the real target list for admins with configuration actions", async () => {
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [target] })),
    );
    const wrapper = await mountPage("admin");

    expect(wrapper.get("h1").text()).toBe("进化对象配置");
    expect(wrapper.text()).toContain("deep-research");
    expect(wrapper.find(".target-create").exists()).toBe(true);
    expect(wrapper.text()).toContain("编辑");
    expect(wrapper.text()).toContain("停用");
    expect(wrapper.text()).toContain("删除");
  });

  it("renders the list for members without write controls", async () => {
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [target] })),
    );
    const wrapper = await mountPage("member");

    expect(wrapper.text()).toContain("deep-research");
    expect(wrapper.find(".target-create").exists()).toBe(false);
    expect(wrapper.find(".row-actions").exists()).toBe(false);
  });

  it("retries a failed target query without replacing the page", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/evolution/targets", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              { error: { code: "INTERNAL", message: "failed" } },
              { status: 500 },
            )
          : HttpResponse.json({ items: [target] });
      }),
    );
    const wrapper = await mountPage("admin");

    expect(wrapper.text()).toContain("进化对象配置读取失败");
    await wrapper.get(".error-state button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("deep-research");
  });
});
