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
  validationProjectId: "val-deep-research",
  testProjectId: "test-deep-research",
  primaryMetricKey: "resolved_rate",
  enabled: true,
  members: [
    {
      objectType: "skill",
      objectName: "deep-research",
      subDir: "skills/deep-research",
      matchByName: false,
    },
  ],
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
          subDir: "agents/explore",
          enabled: false,
          members: [
            {
              objectType: "agent",
              objectName: "Explore",
              subDir: "agents/explore",
              matchByName: false,
            },
          ],
        })],
        canWrite: true,
      },
    });

    expect(wrapper.text()).toContain("进化对象 / 成员");
    expect(wrapper.text()).toContain("仓库");
    expect(wrapper.text()).toContain("基线");
    expect(wrapper.text()).toContain("测试工程");
    expect(wrapper.text()).toContain("验证集");
    expect(wrapper.text()).toContain("测试集");
    expect(wrapper.text()).toContain("val-deep-research");
    expect(wrapper.text()).toContain("test-deep-research");
    expect(wrapper.text()).toContain("状态");
    expect(wrapper.text()).toContain("操作");
    expect(wrapper.text()).toContain("skill:deep-research");
    expect(wrapper.text()).toContain("agents/explore");
    expect(wrapper.text()).toContain("agent:Explore");
    expect(wrapper.text()).toContain("已启用");
    expect(wrapper.text()).toContain("已停用");
    expect(wrapper.find(".target-table-scroll").exists()).toBe(true);
  });

  it("renders multiple member chips and a +N display name per configuration", () => {
    const wrapper = mount(TargetTable, {
      props: {
        targets: [
          target({
            members: [
              {
                objectType: "skill",
                objectName: "deep-research",
                subDir: "skills/deep-research",
                matchByName: false,
              },
              {
                objectType: "agent",
                objectName: "Explore",
                subDir: "agents/explore",
                matchByName: true,
              },
            ],
          }),
        ],
        canWrite: false,
      },
    });

    expect(wrapper.get(".target-name").text()).toBe("deep-research +1");
    expect(wrapper.findAll(".target-member")).toHaveLength(2);
    expect(wrapper.get(".target-member:nth-child(1)").text()).toContain(
      "skill:deep-research",
    );
    expect(wrapper.get(".target-member:nth-child(2)").text()).toContain(
      "agent:Explore",
    );
  });

  it.each([[1, true, "等待自动重试"], [3, false, "已停止自动重试"]] as const)(
    "renders the persisted binding failure after %i attempts",
    (attempts, willRetry, message) => {
      const wrapper = mount(TargetTable, {
        props: {
          targets: [target({ attributionFailure: { attempts, reason: "invalid_input_or_report", willRetry } })],
          canWrite: false,
        },
      });
      expect(wrapper.get(".binding-failure").text()).toContain("归因输入或报告校验失败");
      expect(wrapper.get(".binding-failure").text()).toContain(message);
    },
  );

  it("shows the configured primary metric key", () => {
    const wrapper = mount(TargetTable, {
      props: {
        targets: [target()],
        canWrite: false,
      },
    });

    expect(wrapper.get('[data-testid="target-primary-metric"]').text()).toBe(
      "resolved_rate",
    );
  });

  it("shows an explicit empty project value for historical rows", () => {
    const wrapper = mount(TargetTable, {
      props: {
        targets: [target({ validationProjectId: "", testProjectId: "" })],
        canWrite: false,
      },
    });

    expect(wrapper.text()).toContain("未填写");
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

  it("guides members to an administrator when the collection is empty", () => {
    const wrapper = mount(TargetTable, {
      props: {
        targets: [],
        canWrite: false,
      },
    });

    expect(wrapper.text()).toContain("当前暂无配置，请联系管理员添加或启用对象");
    expect(wrapper.text()).not.toContain("新增一个 skill 或 agent");
  });

  it("guides admins to create the first target when the collection is empty", () => {
    const wrapper = mount(TargetTable, {
      props: {
        targets: [],
        canWrite: true,
      },
    });

    expect(wrapper.text()).toContain("新增一个 skill 或 agent");
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
    expect(wrapper.emitted("edit")).toEqual([[target()]]);
    expect(wrapper.emitted("toggle")).toEqual([[{
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
