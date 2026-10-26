// @vitest-environment jsdom

import type { EvolutionTarget } from "@harness/contracts";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import TargetTable from "./TargetTable.vue";

const target = (overrides: Partial<EvolutionTarget> = {}): EvolutionTarget => ({
  id: "target-1",
  objectType: "skill",
  objectName: "deep-research",
  repoUrl: "https://example.com/skills.git",
  subDir: "skills/deep-research",
  defaultRef: "main",
  enabled: true,
  ...overrides,
});

describe("TargetTable", () => {
  it("renders every configured column and keeps disabled rows visible", () => {
    const wrapper = mount(TargetTable, {
      props: {
        targets: [target(), target({
          id: "target-2",
          objectType: "agent",
          objectName: "Explore",
          enabled: false,
        })],
        canWrite: true,
      },
    });

    expect(wrapper.text()).toContain("对象类型");
    expect(wrapper.text()).toContain("对象名称");
    expect(wrapper.text()).toContain("仓库");
    expect(wrapper.text()).toContain("子目录");
    expect(wrapper.text()).toContain("基线");
    expect(wrapper.text()).toContain("状态");
    expect(wrapper.text()).toContain("操作");
    expect(wrapper.text()).toContain("skill");
    expect(wrapper.text()).toContain("agent");
    expect(wrapper.text()).toContain("已启用");
    expect(wrapper.text()).toContain("已停用");
    expect(wrapper.find(".target-table-scroll").exists()).toBe(true);
  });

  it("hides all write controls from members", () => {
    const wrapper = mount(TargetTable, {
      props: {
        targets: [target()],
        canWrite: false,
      },
    });

    expect(wrapper.find(".target-create").exists()).toBe(false);
    expect(wrapper.find(".row-actions").exists()).toBe(false);
  });

  it("exposes create, edit, toggle, and delete actions to admins", async () => {
    const wrapper = mount(TargetTable, {
      props: {
        targets: [target()],
        canWrite: true,
      },
    });

    expect(wrapper.get(".target-create").text()).toContain("新增配置");
    await wrapper.get(".target-create").trigger("click");
    await wrapper.get(".edit-target").trigger("click");
    await wrapper.get(".toggle-target").trigger("click");
    await wrapper.get(".delete-target").trigger("click");

    expect(wrapper.emitted("create")).toHaveLength(1);
    expect(wrapper.emitted("edit")).toEqual([[target()], [{
      ...target(),
      enabled: false,
    }]]);
    expect(wrapper.emitted("delete")).toEqual([[target()]]);
  });

  it("keeps loading, empty, error, and retry states distinct", async () => {
    const loading = mount(TargetTable, {
      props: { targets: [], loading: true, canWrite: false },
    });
    expect(loading.get("[role='status']").attributes("aria-label")).toBe(
      "正在读取进化对象配置",
    );

    const empty = mount(TargetTable, {
      props: { targets: [], canWrite: false },
    });
    expect(empty.text()).toContain("暂无进化对象配置");

    const error = mount(TargetTable, {
      props: {
        targets: [],
        error: new Error("failed"),
        canWrite: false,
      },
    });
    expect(error.text()).toContain("进化对象配置读取失败");
    await error.get("button").trigger("click");
    expect(error.emitted("retry")).toHaveLength(1);
  });
});
