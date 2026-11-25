// @vitest-environment jsdom

import type { EvolutionTarget } from "@harness/contracts";
import { flushPromises, mount } from "@vue/test-utils";
import { ElAutocomplete } from "element-plus/es/components/autocomplete/index";
import ElDialog from "element-plus/es/components/dialog/index";
import { describe, expect, it } from "vitest";

import { elementPlusComponents } from "../../../../test/setup";
import TargetFormDialog from "./TargetFormDialog.vue";

const target: EvolutionTarget = {
  id: "target-1",
  objectType: "skill",
  objectName: "deep-research",
  repoUrl: "https://example.com/skills.git",
  subDir: "skills/deep-research",
  defaultRef: "main",
  validationProjectId: "val-deep-research",
  testProjectId: "test-deep-research",
  primaryMetricKey: "resolved_rate",
  enabled: true,
};

async function mountDialog(overrides: Record<string, unknown> = {}) {
  const wrapper = mount(TargetFormDialog, {
    props: {
      modelValue: true,
      target: null,
      versions: [],
      versionsLoading: false,
      submitting: false,
      serverError: null,
      ...overrides,
    },
    global: {
      components: elementPlusComponents,
    },
    attachTo: document.body,
  });
  await flushPromises();
  return wrapper;
}

async function fillRequired(
  wrapper: Awaited<ReturnType<typeof mountDialog>>,
  values: {
    objectName?: string;
    repoUrl?: string;
    subDir?: string;
    defaultRef?: string;
    validationProjectId?: string;
    testProjectId?: string;
    primaryMetricKey?: string;
  } = {},
) {
  await wrapper.get('input[name="objectName"]').setValue(
    values.objectName ?? "  deep-research  ",
  );
  await wrapper.get('input[name="repoUrl"]').setValue(
    values.repoUrl ?? "  https://example.com/skills.git  ",
  );
  await wrapper.get('input[name="subDir"]').setValue(
    values.subDir ?? "  skills/deep-research  ",
  );
  await wrapper
    .get('input[name="defaultRef"]')
    .setValue(values.defaultRef ?? "  main  ");
  await wrapper
    .get('input[name="validationProjectId"]')
    .setValue(values.validationProjectId ?? "  val-2026-q3  ");
  await wrapper
    .get('input[name="testProjectId"]')
    .setValue(values.testProjectId ?? "  test-2026-q3  ");
  await wrapper
    .get('input[name="primaryMetricKey"]')
    .setValue(values.primaryMetricKey ?? "  resolved_rate  ");
  await flushPromises();
}

describe("TargetFormDialog", () => {
  it("uses the prototype modal width and head, body, and footer regions", async () => {
    const wrapper = await mountDialog();

    expect(wrapper.findComponent(ElDialog).props("width")).toBe(
      "min(720px, calc(100vw - 32px))",
    );
    expect(wrapper.find(".target-dialog-head").exists()).toBe(true);
    expect(wrapper.find(".target-dialog-body form").exists()).toBe(true);
    expect(wrapper.find(".target-dialog-foot .form-actions").exists()).toBe(true);
  });

  it.each([
    { previous: "legacy-prompt", label: "legacy-prompt" },
    { previous: null, label: "未绑定" },
  ])("preserves the original Skill selection $label when editing a target", async ({ previous, label }) => {
    const wrapper = await mountDialog({
      target: { ...target, attributionSkillName: previous, attributionPackageId: null },
    });
    expect(wrapper.get("select[aria-label='归因 Skill'] option:checked").text()).toBe(label);
    await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({ attributionPackageId: null });
  });

  it("can create an unbound rule target or prebind a Skill while the Agent is disabled", async () => {
    const wrapper = await mountDialog({ runtimeEnabled: false });
    await fillRequired(wrapper);
    const select = wrapper.get("select[aria-label='归因 Skill']");
    expect(select.get("option:checked").text()).toContain("内置归因规则");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({ attributionPackageId: null });
    await select.setValue("default-attribute-badcases");
    expect(wrapper.text()).toContain("运行时恢复并重启后开始后台归因");
    await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("submit")?.[1]?.[0]).toMatchObject({ attributionPackageId: "default-attribute-badcases" });
    wrapper.unmount();
  });

  it("selects the default after runtime capability loads without resetting other fields", async () => {
    const wrapper = await mountDialog({ packagesLoading: true });
    await fillRequired(wrapper);
    await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("submit")).toBeUndefined();
    await wrapper.setProps({ runtimeEnabled: true, packagesLoading: false });
    await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      attributionPackageId: "default-attribute-badcases", objectName: "deep-research",
    });
    wrapper.unmount();
  });

  it("submits trimmed create values", async () => {
    const wrapper = await mountDialog({ runtimeEnabled: true });
    await fillRequired(wrapper);
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.emitted("submit")).toEqual([[
      {
        attributionPackageId: "default-attribute-badcases",
        objectType: "skill",
        objectName: "deep-research",
        repoUrl: "https://example.com/skills.git",
        subDir: "skills/deep-research",
        defaultRef: "main",
        validationProjectId: "val-2026-q3",
        testProjectId: "test-2026-q3",
        primaryMetricKey: "resolved_rate",
        enabled: true,
      },
    ]]);
  });

  it("keeps directly typed baseline text after blur and submit", async () => {
    const wrapper = await mountDialog();
    await fillRequired(wrapper, {
      defaultRef: "  feature/direct-submit  ",
    });

    const input = wrapper.get('input[name="defaultRef"]');
    expect((input.element as HTMLInputElement).value).toBe(
      "  feature/direct-submit  ",
    );

    await input.trigger("blur");
    expect((input.element as HTMLInputElement).value).toBe(
      "  feature/direct-submit  ",
    );

    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      defaultRef: "feature/direct-submit",
    });
  });

  it("shows inline required errors and does not submit empty fields", async () => {
    const wrapper = await mountDialog();
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("请填写对象名称");
    expect(wrapper.text()).toContain("请填写仓库地址");
    expect(wrapper.text()).toContain("请填写子目录");
    expect(wrapper.text()).toContain("请填写基线分支或标签");
    expect(wrapper.text()).toContain("请填写验证集测试工程 ID");
    expect(wrapper.text()).toContain("请填写测试集测试工程 ID");
    expect(wrapper.text()).toContain("请填写主指标 key");
    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  it("rejects project IDs containing whitespace", async () => {
    const wrapper = await mountDialog();
    await fillRequired(wrapper, {
      validationProjectId: "val 2026",
      testProjectId: "test\t2026",
      primaryMetricKey: "resolved rate",
    });
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.text()).toContain("工程 ID 不能包含空格或控制字符");
    expect(wrapper.text()).toContain("主指标 key 不能包含空格或控制字符");
    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  it("keeps entered values when a server error is rendered", async () => {
    const wrapper = await mountDialog({
      serverError: {
        summary: "仓库或 ref 无效，请检查地址、子目录与基线",
      },
    });
    await fillRequired(wrapper, {
      repoUrl: "https://example.com/entered.git",
    });

    expect(wrapper.get("[role='alert']").text()).toContain(
      "仓库或 ref 无效，请检查地址、子目录与基线",
    );
    expect(
      (wrapper.get('input[name="repoUrl"]').element as HTMLInputElement).value,
    ).toBe("https://example.com/entered.git");
  });

  it("renders a structured field error, suggestion, and focuses the field", async () => {
    const wrapper = await mountDialog();
    await wrapper.setProps({
      serverError: {
        summary: "仓库地址不能包含用户名或密码",
        field: "repoUrl",
        reason: "repo_url_credentials",
        message: "仓库地址不能包含用户名或密码",
        suggestion: "移除 URL 中的凭据，改用 SSH agent 或凭据助手。",
      },
    });
    await flushPromises();

    const input = wrapper.get('input[name="repoUrl"]');
    expect(input.attributes("aria-invalid")).toBe("true");
    expect(input.attributes("aria-describedby")).toBe("target-repoUrl-error");
    expect(wrapper.get("#target-repoUrl-error").text()).toContain(
      "仓库地址不能包含用户名或密码",
    );
    expect(wrapper.get("#target-repoUrl-error").text()).toContain(
      "移除 URL 中的凭据",
    );
    expect(document.activeElement).toBe(input.element);
  });

  it("clears a server field error once the offending field changes", async () => {
    const wrapper = await mountDialog({
      serverError: {
        summary: "仓库地址格式不正确",
        field: "repoUrl",
        message: "仓库地址格式不正确",
        suggestion: "使用无凭据的 HTTPS 或 SSH 地址。",
      },
    });
    expect(wrapper.find("[role='alert']").exists()).toBe(true);

    await wrapper
      .get('input[name="repoUrl"]')
      .setValue("https://example.com/next.git");
    await flushPromises();

    expect(wrapper.find("[role='alert']").exists()).toBe(false);
    expect(
      wrapper.get('input[name="repoUrl"]').attributes("aria-invalid"),
    ).toBeUndefined();
  });

  it("renders bounded git command output in a collapsible block", async () => {
    const wrapper = await mountDialog({
      serverError: {
        summary: "无法访问仓库",
        field: "repoUrl",
        message: "无法访问仓库",
        suggestion: "确认地址、网络与读取权限；下方是脱敏后的 git 输出。",
        command: { name: "git ls-remote", exitCode: 128 },
        output:
          "fatal: unable to access 'https://git.example.com/repo.git/': Could not resolve host",
      },
    });

    const block = wrapper.get("[data-testid='target-git-output']");
    expect(block.element.tagName).toBe("DETAILS");
    expect(block.text()).toContain("git ls-remote");
    expect(block.text()).toContain("退出码 128");
    expect(block.get("pre").text()).toContain("Could not resolve host");
  });

  it("shows definition snapshot guidance only when the target is bound", async () => {
    const wrapper = await mountDialog({ runtimeEnabled: false });
    const guidance = "保存绑定时从指定版本读取此目录的对象定义";
    expect(wrapper.text()).not.toContain(guidance);
    await wrapper.get("select[aria-label='归因 Skill']").setValue("default-attribute-badcases");
    expect(wrapper.text()).toContain(guidance);
    wrapper.unmount();
  });

  it("shows the pinned commit, definition path and preview on edit", async () => {
    const definition = { commit: "a".repeat(40), path: "agents/example/AGENT.md", preview: "Agent instructions" };
    const wrapper = await mountDialog({ target: { ...target, definition } });
    expect(wrapper.text()).toContain(definition.commit);
    expect(wrapper.text()).toContain(definition.path);
    expect(wrapper.get(".definition-preview").text()).toBe(definition.preview);
  });

  it("prefills edits, exposes remote suggestions and submits disabled state", async () => {
    const wrapper = await mountDialog({
      target,
      versions: ["main", "v1.9.0", "v2.0.0"],
    });

    expect(
      (wrapper.get('input[name="objectName"]').element as HTMLInputElement).value,
    ).toBe("deep-research");
    expect(
      (wrapper.get('input[name="defaultRef"]').element as HTMLInputElement).value,
    ).toBe("main");
    expect(
      (
        wrapper.get('input[name="validationProjectId"]')
          .element as HTMLInputElement
      ).value,
    ).toBe("val-deep-research");
    expect(
      (
        wrapper.get('input[name="testProjectId"]').element as HTMLInputElement
      ).value,
    ).toBe("test-deep-research");
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
    expect(wrapper.get(".el-switch").classes()).toContain("is-checked");

    await wrapper.get(".el-switch").trigger("click");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      objectName: "deep-research",
      enabled: false,
    });
  });

  it("keeps tag suggestions available when the saved baseline is a branch", async () => {
    const wrapper = await mountDialog({
      target: {
        ...target,
        defaultRef: "feature/manual-direct",
      },
      versions: ["v1.9.0", "v2.0.0"],
    });

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
        ).fetchSuggestions("feature/manual-direct", resolve);
      },
    );

    expect(suggestions.map(({ value }) => value)).toEqual([
      "feature/manual-direct",
      "v1.9.0",
      "v2.0.0",
    ]);
  });

  it("opens suggestions from the visible toggle and selects an option", async () => {
    const wrapper = await mountDialog({
      target,
      versions: ["v1.9.0", "v2.0.0"],
    });

    const toggle = wrapper.get('button[aria-label="展开标签建议"]');
    await toggle.trigger("mousedown");
    await toggle.trigger("click");
    await flushPromises();

    const options = Array.from(
      document.body.querySelectorAll<HTMLElement>('[role="option"]'),
    );
    const option = options.find((item) => item.textContent === "v2.0.0");
    expect(option).toBeDefined();
    option?.click();
    await flushPromises();

    expect(
      (wrapper.get('input[name="defaultRef"]').element as HTMLInputElement).value,
    ).toBe("v2.0.0");
  });

  it("selects a focused suggestion with the keyboard", async () => {
    const wrapper = await mountDialog({
      target,
      versions: ["v1.9.0", "v2.0.0"],
    });
    const input = wrapper.get('input[name="defaultRef"]');

    const toggle = wrapper.get('button[aria-label="展开标签建议"]');
    await toggle.trigger("mousedown");
    await toggle.trigger("click");
    await flushPromises();
    await input.trigger("keydown", { key: "ArrowDown" });
    await input.trigger("keydown", { key: "ArrowDown" });
    await input.trigger("keydown", { key: "Enter" });
    await flushPromises();

    expect((input.element as HTMLInputElement).value).toBe("v1.9.0");
  });

  it("clears a stale baseline error as soon as one valid character is typed", async () => {
    const wrapper = await mountDialog();
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("请填写基线分支或标签");

    await wrapper.get('input[name="defaultRef"]').setValue("f");
    await flushPromises();

    expect(wrapper.text()).not.toContain("请填写基线分支或标签");
  });

  it("resets stale values and errors when reopened for create", async () => {
    const wrapper = await mountDialog({
      target,
      serverError: { summary: "对象配置已存在" },
    });
    await wrapper.setProps({
      target: null,
      serverError: null,
    });
    await flushPromises();

    expect(
      (wrapper.get('input[name="objectName"]').element as HTMLInputElement).value,
    ).toBe("");
    expect(wrapper.find("[role='alert']").exists()).toBe(false);
  });

  it("only shows remote loading for an editable target", async () => {
    const createWrapper = await mountDialog({
      target: null,
      versionsLoading: true,
    });
    expect(createWrapper.text()).not.toContain("正在读取仓库版本");

    const editWrapper = await mountDialog({
      target,
      versionsLoading: true,
    });
    expect(editWrapper.text()).toContain("正在读取仓库版本");
  });

  it("allows direct input when version suggestions fail", async () => {
    const wrapper = await mountDialog({
      target,
      versionsError: true,
    });

    expect(wrapper.text()).toContain("暂时无法获取标签建议，可直接输入");
    await wrapper
      .get('input[name="defaultRef"]')
      .setValue("feature/offline-fallback");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      defaultRef: "feature/offline-fallback",
    });
  });

  it("marks tag suggestions as saved-config data when the draft repo changes", async () => {
    const wrapper = await mountDialog({
      target,
      versions: ["v2.0.0"],
    });

    await wrapper
      .get('input[name="repoUrl"]')
      .setValue("https://example.com/changed.git");

    expect(wrapper.text()).toContain("标签建议来自已保存配置");
  });
});
