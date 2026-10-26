// @vitest-environment jsdom

import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import type { EvolutionTarget } from "@harness/contracts";
import { ElOption, ElSelect } from "element-plus/es/components/select/index";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { createAppRouter } from "../../../router";
import { useAuthStore } from "../../../stores/auth";
import { server } from "../../../test/server";
import { elementPlusComponents } from "../../../test/setup";
import TargetConfigPage from "./Index.vue";
import TargetFormDialog from "./components/TargetFormDialog.vue";

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
      components: elementPlusComponents,
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

  it("creates an admin target and closes the form after success", async () => {
    let submitted: unknown;
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [] })),
      http.post("/api/evolution/targets", async ({ request }) => {
        submitted = await request.json();
        return HttpResponse.json(
          {
            id: "target-created",
            ...(submitted as object),
          },
          { status: 201 },
        );
      }),
    );
    const wrapper = await mountPage("admin");

    await wrapper.get(".target-create").trigger("click");
    await wrapper.get('input[name="objectName"]').setValue("deep-research");
    await wrapper
      .get('input[name="repoUrl"]')
      .setValue("https://example.com/skills.git");
    await wrapper
      .get('input[name="subDir"]')
      .setValue("skills/deep-research");
    wrapper.findComponent(ElSelect).vm.$emit("update:modelValue", "main");
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(submitted).toEqual({
      objectType: "skill",
      objectName: "deep-research",
      repoUrl: "https://example.com/skills.git",
      subDir: "skills/deep-research",
      defaultRef: "main",
      enabled: true,
    });
    expect(wrapper.getComponent(TargetFormDialog).props("modelValue")).toBe(false);
  });

  it("keeps the admin form open and preserves values on REPO_INVALID", async () => {
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [] })),
      http.post("/api/evolution/targets", () =>
        HttpResponse.json(
          {
            error: {
              code: "REPO_INVALID",
              message: "repository or ref is invalid",
            },
          },
          { status: 422 },
        )),
    );
    const wrapper = await mountPage("admin");

    await wrapper.get(".target-create").trigger("click");
    await wrapper.get('input[name="objectName"]').setValue("deep-research");
    await wrapper
      .get('input[name="repoUrl"]')
      .setValue("https://example.com/skills.git");
    await wrapper
      .get('input[name="subDir"]')
      .setValue("skills/deep-research");
    wrapper.findComponent(ElSelect).vm.$emit("update:modelValue", "main");
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get("[role='alert']").text()).toContain(
      "仓库或 ref 无效，请检查地址、子目录与基线",
    );
    expect(
      (wrapper.get('input[name="repoUrl"]').element as HTMLInputElement).value,
    ).toBe("https://example.com/skills.git");
  });

  it("loads target versions for edit mode", async () => {
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [target] })),
      http.get("/api/evolution/targets/:targetId/versions", () =>
        HttpResponse.json({
          versions: ["main", "v1.9.0", "v2.0.0"],
          defaultRef: "main",
        })),
    );
    const wrapper = await mountPage("admin");

    await wrapper.get(".edit-target").trigger("click");
    await flushPromises();

    expect(wrapper.findComponent(ElSelect).props("modelValue")).toBe("main");
    expect(
      wrapper
        .findAllComponents(ElOption)
        .map((option) => option.props("value")),
    ).toEqual(["main", "v1.9.0", "v2.0.0"]);
  });

  it("maps TARGET_EXISTS into the open edit form", async () => {
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [target] })),
      http.get("/api/evolution/targets/:targetId/versions", () =>
        HttpResponse.json({ versions: ["main"], defaultRef: "main" })),
      http.put("/api/evolution/targets/:targetId", () =>
        HttpResponse.json(
          {
            error: {
              code: "TARGET_EXISTS",
              message: "target already exists",
            },
          },
          { status: 409 },
        )),
    );
    const wrapper = await mountPage("admin");

    await wrapper.get(".edit-target").trigger("click");
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get("[role='alert']").text()).toContain(
      "同类型的对象名称已经配置",
    );
    expect(wrapper.getComponent(TargetFormDialog).props("modelValue")).toBe(true);
  });
});
