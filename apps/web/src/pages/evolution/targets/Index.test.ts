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

const workspaceId = "ws-test";
const ws = `/workspaces/${workspaceId}`;
const base = `/api/workspaces/${workspaceId}/evolution/targets`;
import { signInWithWorkspace } from "../../../test/auth";
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
  signInWithWorkspace({
    id: "user-1",
    username: role,
    displayName: role,
    role,
    mustChangePassword: false,
  });
  const router = createAppRouter();
  await router.push(`${ws}/evolution/targets`);
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
      http.get(base, () =>
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
      http.get(base, () =>
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
    expect(back.props("to")).toBe(`${ws}/evolution`);
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
    ).toBe(`${ws}/evolution`);
  });

  it("uses the prototype page hierarchy without an extra eyebrow", async () => {
    server.use(
      http.get(base, () =>
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
      http.get(base, () =>
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
      http.get(base, () => {
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
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.post(base, async ({ request }) => {
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
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.post(base, () =>
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

  it("anchors structured REPO_INVALID details to the failing field", async () => {
    server.use(
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.post(base, () =>
        HttpResponse.json(
          {
            error: {
              code: "REPO_INVALID",
              message: "repository or ref is invalid",
              details: {
                field: "repoUrl",
                reason: "repo_url_credentials",
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
      .setValue("https://user:secret@example.com/skills.git");
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
      "仓库地址不能包含用户名或密码",
    );
    expect(wrapper.get("#target-repoUrl-error").text()).toContain(
      "移除 URL 中的凭据",
    );
    const input = wrapper.get('input[name="repoUrl"]');
    expect(input.attributes("aria-invalid")).toBe("true");
    expect(input.attributes("aria-describedby")).toBe("target-repoUrl-error");
    expect((input.element as HTMLInputElement).value).toBe(
      "https://user:secret@example.com/skills.git",
    );
    expect(wrapper.getComponent(TargetFormDialog).props("modelValue")).toBe(true);
  });

  it("shows the exit code and redacted output for an unreachable remote", async () => {
    server.use(
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.post(base, () =>
        HttpResponse.json(
          {
            error: {
              code: "REPO_INVALID",
              message: "repository or ref is invalid",
              details: {
                field: "repoUrl",
                reason: "repo_unreachable",
                command: { name: "git ls-remote", exitCode: 128 },
                output:
                  "fatal: unable to access 'https://git.example.com/repo.git/': Could not resolve host",
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
      .setValue("https://git.example.com/repo.git");
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

    expect(wrapper.get("[role='alert']").text()).toContain("无法访问仓库");
    const block = wrapper.get("[data-testid='target-git-output']");
    expect(block.text()).toContain("git ls-remote");
    expect(block.text()).toContain("退出码 128");
    expect(block.get("pre").text()).toContain("Could not resolve host");
  });

  it("keeps a missing baseline distinct from an unreachable repository", async () => {
    server.use(
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.post(base, () =>
        HttpResponse.json(
          {
            error: {
              code: "REPO_INVALID",
              message: "repository or ref is invalid",
              details: {
                field: "defaultRef",
                reason: "ref_not_found",
                command: { name: "git ls-remote", exitCode: 2 },
                output: "fatal: couldn't find remote ref feature/missing",
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
      .setValue("https://git.example.com/repo.git");
    await wrapper
      .get('input[name="subDir"]')
      .setValue("skills/deep-research");
    await wrapper.get('input[name="defaultRef"]').setValue("feature/missing");
    await wrapper
      .get('input[name="validationProjectId"]')
      .setValue("val-2026-q3");
    await wrapper.get('input[name="testProjectId"]').setValue("test-2026-q3");
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get("#target-defaultRef-error").text()).toContain(
      "仓库可达，但找不到该 ref",
    );
    expect(wrapper.get("[role='alert']").text()).not.toContain(
      "检查地址、子目录与基线",
    );
    expect(wrapper.get("[data-testid='target-git-output']").text()).toContain(
      "退出码 2",
    );
  });

  it("falls back to shared guidance for an unknown REPO_INVALID reason", async () => {
    server.use(
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.post(base, () =>
        HttpResponse.json(
          {
            error: {
              code: "REPO_INVALID",
              message: "repository or ref is invalid",
              details: { field: "repoUrl", reason: "future_reason" },
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
  });

  it("maps PROJECT_ID_INVALID into the open form", async () => {
    server.use(
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.post(base, () =>
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
      "测试工程 ID 无效",
    );
    expect(wrapper.get("#target-validationProjectId-error").text()).toContain(
      "测试工程 ID 无效",
    );
    expect(
      wrapper
        .get('input[name="validationProjectId"]')
        .attributes("aria-invalid"),
    ).toBe("true");
    expect(wrapper.getComponent(TargetFormDialog).props("modelValue")).toBe(true);
  });

  it("hides an unknown save failure behind the shared save guidance", async () => {
    server.use(
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.post(base, () =>
        HttpResponse.json(
          {
            error: {
              code: "INTERNAL",
              message: "repository probe failed",
            },
          },
          { status: 500 },
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

    expect(wrapper.get("[role='alert']").text()).toBe(
      "服务暂时不可用，请稍后重试；若持续失败请联系管理员。",
    );
    expect(wrapper.text()).not.toContain("repository probe failed");
    expect(wrapper.getComponent(TargetFormDialog).props("modelValue")).toBe(true);
  });

  it("loads target versions for edit mode", async () => {
    server.use(
      http.get(base, () =>
        HttpResponse.json({ items: [target] })),
      http.get(`${base}/:targetId/versions`, () =>
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
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.get(`${base}/:targetId/versions`, () => {
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
      http.get(base, () =>
        HttpResponse.json({ items: [target] })),
      http.get(`${base}/:targetId/versions`, () =>
        HttpResponse.json({ versions: ["main"], defaultRef: "main" })),
      http.put(`${base}/:targetId`, () =>
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

  it("maps TARGET_CONTENT_UNRESOLVED into actionable form guidance", async () => {
    server.use(
      http.get(base, () =>
        HttpResponse.json({ items: [] })),
      http.post(base, () =>
        HttpResponse.json(
          {
            error: {
              code: "TARGET_CONTENT_UNRESOLVED",
              message: "target content could not be resolved to a body hash",
              details: { targetType: "skill", reason: "content_not_found" },
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
    await wrapper.get('input[name="defaultRef"]').setValue("v9.9.9");
    await wrapper
      .get('input[name="validationProjectId"]')
      .setValue("val-2026-q3");
    await wrapper.get('input[name="testProjectId"]').setValue("test-2026-q3");
    await flushPromises();
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    const error = wrapper.get("[data-testid='target-server-error']");
    expect(error.text()).toContain("无法读取该基线下的目标文件内容");
    expect(error.text()).toContain("body hash");
    expect(error.text()).not.toContain("target content could not");
    expect(wrapper.getComponent(TargetFormDialog).props("modelValue")).toBe(true);
  });

  it("cancels target deletion without sending a request", async () => {
    let deletes = 0;
    vi.spyOn(ElMessageBox, "confirm").mockRejectedValue("cancel");
    server.use(
      http.get(base, () =>
        HttpResponse.json({ items: [target] })),
      http.delete(`${base}/:targetId`, () => {
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
      http.get(base, () => {
        reads += 1;
        return HttpResponse.json({ items: reads === 1 ? [target] : [] });
      }),
      http.delete(`${base}/:targetId`, () => {
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
      http.get(base, () =>
        HttpResponse.json({ items: [target] })),
      http.delete(`${base}/:targetId`, () =>
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
      http.get(base, () =>
        HttpResponse.json({ items: [target] })),
      http.put(`${base}/:targetId`, async ({ request }) => {
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
