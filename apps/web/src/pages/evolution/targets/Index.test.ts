// @vitest-environment jsdom

import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import type { EvolutionTarget } from "@harness/contracts";
import { ElAutocomplete } from "element-plus/es/components/autocomplete/index";
import { ElMessageBox } from "element-plus/es/components/message-box/index";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import type { Component } from "vue";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import type { Router } from "vue-router";
import { RouterLink } from "vue-router";

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
  validationProjectId: "val-deep-research",
  testProjectId: "test-deep-research",
  enabled: true,
};

async function mountPage(
  role: "admin" | "member",
  stubs: Record<string, Component> = {},
) {
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
      stubs,
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
  vi.restoreAllMocks();
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
    expect(wrapper.text()).toContain("测试工程");
    expect(wrapper.text()).toContain("验证集");
    expect(wrapper.text()).toContain("val-deep-research");
    expect(wrapper.text()).toContain("test-deep-research");
    expect(wrapper.find(".target-create").exists()).toBe(true);
    expect(wrapper.text()).toContain("编辑");
    expect(wrapper.text()).toContain("停用");
    expect(wrapper.text()).toContain("删除");
  });

  it("links back to the evolution page from the page head", async () => {
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [target] })),
    );
    // jsdom 的 history.pushState 支持客户端导航；这里把 RouterLink
    // stub 成点击即 $router.push(to) 的真 <a>，让用例能回归「点击返回
    // 入口确实导航到 /evolution」这一行为而不只是链接属性。
    const wrapper = await mountPage("admin", {
      RouterLink: {
        props: ["to"],
        template: `<a :href="to" @click.prevent="$router.push(to)"><slot /></a>`,
      },
    });

    const back = wrapper.getComponent(RouterLink);
    expect(back.props("to")).toBe("/evolution");
    expect(back.text()).toContain("返回自进化");
    expect(
      (back.element as HTMLAnchorElement).dataset.testid,
    ).toBe("target-config-back");
    await back.trigger("click");
    await flushPromises();
    await vi.dynamicImportSettled();
    await flushPromises();
    expect(
      (wrapper.vm.$router as Router).currentRoute.value.path,
    ).toBe("/evolution");
  });

  it("uses the prototype page hierarchy without an extra eyebrow", async () => {
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [target] })),
    );
    const wrapper = await mountPage("admin");

    expect(wrapper.find(".eyebrow").exists()).toBe(false);
    expect(wrapper.find(".lede").exists()).toBe(false);
    expect(wrapper.get(".page-head h1").text()).toBe("进化对象配置");
    expect(wrapper.get(".page-note").text()).toContain(
      "配置 skill / agent 的仓库、子目录、基线与测试工程",
    );
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
    await wrapper.get('input[name="defaultRef"]').setValue("main");
    await wrapper
      .get('input[name="validationProjectId"]')
      .setValue("val-2026-q3");
    await wrapper.get('input[name="testProjectId"]').setValue("test-2026-q3");
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(submitted).toEqual({
      objectType: "skill",
      objectName: "deep-research",
      repoUrl: "https://example.com/skills.git",
      subDir: "skills/deep-research",
      defaultRef: "main",
      validationProjectId: "val-2026-q3",
      testProjectId: "test-2026-q3",
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
    await wrapper.get('input[name="defaultRef"]').setValue("main");
    await wrapper
      .get('input[name="validationProjectId"]')
      .setValue("val-2026-q3");
    await wrapper.get('input[name="testProjectId"]').setValue("test-2026-q3");
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

  it("maps PROJECT_ID_INVALID into the open form", async () => {
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [] })),
      http.post("/api/evolution/targets", () =>
        HttpResponse.json(
          {
            error: {
              code: "PROJECT_ID_INVALID",
              message: "test project id is invalid",
              details: {
                field: "validationProjectId",
                reason: "project_id_format",
              },
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
    await wrapper.get('input[name="defaultRef"]').setValue("main");
    await wrapper
      .get('input[name="validationProjectId"]')
      .setValue("val-2026-q3");
    await wrapper.get('input[name="testProjectId"]').setValue("test-2026-q3");
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get("[role='alert']").text()).toContain(
      "测试工程 ID 无效，请检查是否为空、超长或包含空格",
    );
    expect(wrapper.getComponent(TargetFormDialog).props("modelValue")).toBe(true);
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

    expect(
      (wrapper.get('input[name="defaultRef"]').element as HTMLInputElement).value,
    ).toBe("main");
    const autocomplete = wrapper.findComponent(ElAutocomplete);
    const suggestions = await new Promise<Array<{ value: string }>>(
      (resolve) => {
        (
          autocomplete.vm.$props as {
            fetchSuggestions: (
              query: string,
              callback: (items: Array<{ value: string }>) => void,
            ) => void;
          }
        ).fetchSuggestions("", resolve);
      },
    );
    expect(suggestions.map(({ value }) => value)).toEqual([
      "main",
      "v1.9.0",
      "v2.0.0",
    ]);
  });

  it("does not request or show version loading in create mode", async () => {
    let versionRequests = 0;
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [] })),
      http.get("/api/evolution/targets/:targetId/versions", () => {
        versionRequests += 1;
        return HttpResponse.json({ versions: [], defaultRef: "" });
      }),
    );
    const wrapper = await mountPage("admin");

    await wrapper.get(".target-create").trigger("click");
    await flushPromises();

    expect(versionRequests).toBe(0);
    expect(wrapper.text()).not.toContain("正在读取仓库版本");
    expect(wrapper.text()).toContain("可直接输入分支或 tag");
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

  it("cancels target deletion without sending a request", async () => {
    let deletes = 0;
    vi.spyOn(ElMessageBox, "confirm").mockRejectedValue("cancel");
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [target] })),
      http.delete("/api/evolution/targets/:targetId", () => {
        deletes += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const wrapper = await mountPage("admin");

    await wrapper.get(".delete-target").trigger("click");
    await flushPromises();

    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      expect.stringContaining("有进行中 run 时不可删除"),
      "删除进化对象",
      expect.any(Object),
    );
    expect(deletes).toBe(0);
  });

  it("deletes a confirmed target and invalidates the list", async () => {
    let deletes = 0;
    let reads = 0;
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue("confirm" as never);
    server.use(
      http.get("/api/evolution/targets", () => {
        reads += 1;
        return HttpResponse.json({ items: reads === 1 ? [target] : [] });
      }),
      http.delete("/api/evolution/targets/:targetId", () => {
        deletes += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const wrapper = await mountPage("admin");

    await wrapper.get(".delete-target").trigger("click");
    await flushPromises();

    expect(deletes).toBe(1);
    expect(reads).toBeGreaterThan(1);
    expect(wrapper.text()).toContain("暂无进化对象配置");
  });

  it("keeps TARGET_IN_USE visible and preserves the row", async () => {
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue("confirm" as never);
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [target] })),
      http.delete("/api/evolution/targets/:targetId", () =>
        HttpResponse.json(
          {
            error: {
              code: "TARGET_IN_USE",
              message: "target is in use",
            },
          },
          { status: 409 },
        )),
    );
    const wrapper = await mountPage("admin");

    await wrapper.get(".delete-target").trigger("click");
    await flushPromises();

    expect(wrapper.get("[role='alert']").text()).toContain(
      "该对象有进行中 run，不能删除",
    );
    expect(wrapper.text()).toContain("deep-research");
  });

  it("persists an enabled toggle through the update mutation", async () => {
    let updates = 0;
    let submitted: unknown;
    server.use(
      http.get("/api/evolution/targets", () =>
        HttpResponse.json({ items: [target] })),
      http.put("/api/evolution/targets/:targetId", async ({ request }) => {
        updates += 1;
        submitted = await request.json();
        return HttpResponse.json({
          ...target,
          ...(submitted as object),
        });
      }),
    );
    const wrapper = await mountPage("admin");

    await wrapper.get(".toggle-target").trigger("click");
    await flushPromises();

    expect(updates).toBe(1);
    expect(submitted).toEqual({
      objectType: "skill",
      objectName: "deep-research",
      repoUrl: "https://example.com/skills.git",
      subDir: "skills/deep-research",
      defaultRef: "main",
      validationProjectId: "val-deep-research",
      testProjectId: "test-deep-research",
      enabled: false,
    });
  });
});
