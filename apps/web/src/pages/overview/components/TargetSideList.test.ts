// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type {
  TargetOverviewDisabledItem,
  TargetOverviewItem,
} from "@harness/contracts";
import TargetSideList from "./TargetSideList.vue";

function disabledItem(): TargetOverviewDisabledItem {
  return {
    targetId: "retired-target",
    objectType: "skill",
    objectName: "release-notes",
    attributionSkillName: "attribute-badcases",
    defaultRef: "v1.2.3",
  };
}

function item(index: number): TargetOverviewItem {
  return {
    targetId: `target-${index}`,
    objectType: "skill",
    objectName: `target-${index}`,
    versions: [`v${index}`, "main"],
    versionOptions: [
      { version: `v${index}`, ref: "release", commit: "a3f9c21" },
      { version: "main", ref: "main", commit: "7b2e084" },
    ],
    sessions: index,
    potential: index + 1,
    attributed: index,
    nonTarget: 1,
    unanalyzed: 1,
    evolvable: index + 1,
  };
}

describe("TargetSideList", () => {
  it("shows five rows per page and emits paging and selection", async () => {
    const wrapper = mount(TargetSideList, {
      props: {
        items: Array.from({ length: 6 }, (_, index) => item(index + 1)),
        page: 1,
        selected: ["target-2"],
        canManage: true,
      },
    });

    expect(wrapper.findAll("[data-testid^='ov-target-side-item-']")).toHaveLength(5);
    expect(wrapper.get("[data-testid='ov-target-side-item-target-1']").text()).toContain(
      "@release",
    );
    expect(wrapper.get("[data-testid='ov-target-side-item-target-2']").classes()).toContain(
      "selected",
    );
    await wrapper.get("[data-testid='ov-target-side-next']").trigger("click");
    expect(wrapper.emitted("update:page")?.at(-1)).toEqual([2]);
    await wrapper.get("[data-testid='ov-target-side-item-target-1'] .select").trigger("click");
    expect(wrapper.emitted("toggle")?.at(-1)).toEqual(["target-1"]);
    await wrapper.get("[data-testid='ov-target-side-edit-target-1']").trigger("click");
    expect(wrapper.emitted("edit")?.at(-1)?.[0]).toMatchObject({
      targetId: "target-1",
    });
    await wrapper.get("[data-testid='ov-target-side-remove-target-1']").trigger("click");
    expect(wrapper.emitted("remove")?.at(-1)?.[0]).toMatchObject({
      targetId: "target-1",
    });
    await wrapper.get("[data-testid='ov-target-side-create']").trigger("click");
    expect(wrapper.emitted("create")).toHaveLength(1);
  });

  it("hides management actions for readers and prompts configuration when empty", async () => {
    const wrapper = mount(TargetSideList, {
      props: { items: [], canManage: false },
    });

    expect(wrapper.find("[data-testid='ov-target-side-empty']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='ov-target-side-create']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='ov-target-side-empty-create']").exists()).toBe(false);
  });

  it("renders the loading and error states", () => {
    const loading = mount(TargetSideList, {
      props: { items: [], loading: true },
    });
    expect(loading.find("[data-testid='ov-target-side-loading']").exists()).toBe(true);

    const failed = mount(TargetSideList, {
      props: { items: [], error: new Error("boom"), code: "OVERVIEW_TARGETS_UNAVAILABLE" },
    });
    expect(failed.find("[data-testid='ov-target-side-error']").exists()).toBe(true);
    expect(failed.text()).toContain("OVERVIEW_TARGETS_UNAVAILABLE");
  });

  it("appends a greyed disabled group after the enabled rows and emits its actions", async () => {
    const wrapper = mount(TargetSideList, {
      props: {
        items: [item(1)],
        disabled: [disabledItem()],
        canManage: true,
      },
    });

    expect(wrapper.get("[data-testid='ov-target-side-disabled-group']").text()).toContain(
      "已停用对象 · 仅展示，不参与统计",
    );
    const row = wrapper.get("[data-testid='ov-target-side-disabled-row-retired-target']");
    expect(row.classes()).toContain("is-disabled");
    expect(row.text()).toContain("release-notes");
    expect(row.text()).toContain("@v1.2.3");
    expect(row.text()).toContain("已停用");
    expect(row.text()).toContain("归因 Skill · attribute-badcases");
    expect(row.text()).toContain("保留配置");
    expect(
      wrapper.get("[data-testid='ov-target-side-disabled-group']").text(),
    ).toContain("不参与统计");
    expect(row.find(".select").exists()).toBe(false);
    expect(row.find(".selected").exists()).toBe(false);
    expect(wrapper.get("[data-testid='ov-target-side-pager']").text()).toContain(
      "共 2 个 · 1 个已停用",
    );

    await wrapper
      .get("[data-testid='ov-target-side-enable-retired-target']")
      .trigger("click");
    expect(wrapper.emitted("enable")?.at(-1)?.[0]).toMatchObject({
      targetId: "retired-target",
    });
    await wrapper
      .get("[data-testid='ov-target-side-edit-retired-target']")
      .trigger("click");
    expect(wrapper.emitted("edit")?.at(-1)?.[0]).toMatchObject({
      targetId: "retired-target",
    });
    await wrapper
      .get("[data-testid='ov-target-side-remove-retired-target']")
      .trigger("click");
    expect(wrapper.emitted("remove")?.at(-1)?.[0]).toMatchObject({
      targetId: "retired-target",
    });
  });

  it("pages disabled rows with the enabled ones and keeps readers read-only", () => {
    const firstPage = mount(TargetSideList, {
      props: {
        items: Array.from({ length: 5 }, (_, index) => item(index + 1)),
        disabled: [disabledItem()],
        canManage: true,
      },
    });
    expect(
      firstPage.find("[data-testid='ov-target-side-disabled-row-retired-target']").exists(),
    ).toBe(false);
    expect(firstPage.find("[data-testid='ov-target-side-disabled-group']").exists()).toBe(false);

    const secondPage = mount(TargetSideList, {
      props: {
        items: Array.from({ length: 5 }, (_, index) => item(index + 1)),
        disabled: [disabledItem()],
        page: 2,
        canManage: false,
      },
    });
    expect(
      secondPage.find("[data-testid='ov-target-side-disabled-row-retired-target']").exists(),
    ).toBe(true);
    expect(
      secondPage.find("[data-testid='ov-target-side-enable-retired-target']").exists(),
    ).toBe(false);
    expect(
      secondPage.find("[data-testid='ov-target-side-edit-retired-target']").exists(),
    ).toBe(false);
    expect(
      secondPage.find("[data-testid='ov-target-side-empty']").exists(),
    ).toBe(false);
  });

  it("renders only the disabled group when every target is disabled", () => {
    const wrapper = mount(TargetSideList, {
      props: { items: [], disabled: [disabledItem()] },
    });

    expect(wrapper.find("[data-testid='ov-target-side-empty']").exists()).toBe(false);
    expect(
      wrapper.find("[data-testid='ov-target-side-disabled-row-retired-target']").exists(),
    ).toBe(true);
    expect(wrapper.find("[data-testid='ov-target-side-disabled-group']").exists()).toBe(true);
  });
});
