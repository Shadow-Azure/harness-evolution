// @vitest-environment jsdom

import type { EvolutionTarget } from "@harness/contracts";
import { flushPromises, mount } from "@vue/test-utils";
import ElDialog from "element-plus/es/components/dialog/index";
import { ElOption, ElSelect } from "element-plus/es/components/select/index";
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
  wrapper.findComponent(ElSelect).vm.$emit(
    "update:modelValue",
    values.defaultRef ?? "  main  ",
  );
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

  it("prefills edits, exposes remote versions and submits disabled state", async () => {
    const wrapper = await mountDialog({
      target,
      versions: ["main", "v1.9.0", "v2.0.0"],
    });

    expect(
      (wrapper.get('input[name="objectName"]').element as HTMLInputElement).value,
    ).toBe("deep-research");
    const select = wrapper.findComponent(ElSelect);
    expect(select.props("modelValue")).toBe("main");
    expect(select.props("filterable")).toBe(true);
    expect(select.props("allowCreate")).toBe(true);
    expect(select.props("defaultFirstOption")).toBe(true);
    expect(
      wrapper
        .findAllComponents(ElOption)
        .map((option) => option.props("value")),
    ).toEqual(["main", "v1.9.0", "v2.0.0"]);
    expect(wrapper.get(".el-switch").classes()).toContain("is-checked");

    await wrapper.get(".el-switch").trigger("click");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.emitted("submit")?.[0]?.[0]).toMatchObject({
      objectName: "deep-research",
      enabled: false,
    });
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
});
