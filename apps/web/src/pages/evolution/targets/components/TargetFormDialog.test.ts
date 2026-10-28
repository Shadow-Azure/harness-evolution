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
      serverError: "",
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

  it("submits trimmed create values", async () => {
    const wrapper = await mountDialog();
    await fillRequired(wrapper);
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.emitted("submit")).toEqual([[
      {
        objectType: "skill",
        objectName: "deep-research",
        repoUrl: "https://example.com/skills.git",
        subDir: "skills/deep-research",
        defaultRef: "main",
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
    expect(wrapper.emitted("submit")).toBeUndefined();
  });

  it("keeps entered values when a server error is rendered", async () => {
    const wrapper = await mountDialog({
      serverError: "仓库或 ref 无效，请检查地址、子目录与基线",
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
      serverError: "对象配置已存在",
    });
    await wrapper.setProps({
      target: null,
      serverError: "",
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
