// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { TargetOverviewItemView } from "../../../api/overview";
import TargetSideList from "./TargetSideList.vue";

function item(index: number): TargetOverviewItemView {
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

  it("renders configuration member chips when the backend exposes them", () => {
    const wrapper = mount(TargetSideList, {
      props: {
        items: [
          {
            ...item(1),
            members: [
              { objectType: "skill", objectName: "deep-research", subDir: "skills/deep-research" },
              { objectType: "skill", objectName: "code-review", subDir: "skills/code-review" },
            ],
          },
        ],
      },
    });

    const members = wrapper.get("[data-testid='ov-target-side-members']");
    expect(members.text()).toContain("skill:deep-research");
    expect(members.text()).toContain("skill:code-review");
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
});
