// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import TargetMultiSelect from "./TargetMultiSelect.vue";

const options = [
  { id: "target-1", name: "synthetic-review", objectType: "skill" as const },
  { id: "target-2", name: "review-agent", objectType: "agent" as const },
];

describe("TargetMultiSelect", () => {
  it("toggles, selects all, clears, and searches options", async () => {
    const wrapper = mount(TargetMultiSelect, {
      props: { options, selected: ["target-1"] },
    });

    expect(wrapper.text()).toContain("已选 1 个进化对象");
    await wrapper.get("[data-testid='ov-target-option-target-2']").setValue(true);
    expect(wrapper.emitted("update:selected")?.at(-1)).toEqual([
      ["target-1", "target-2"],
    ]);

    await wrapper.get("[data-testid='ov-target-select-all']").trigger("click");
    expect(wrapper.emitted("update:selected")?.at(-1)).toEqual([
      ["target-1", "target-2"],
    ]);

    await wrapper.get("[data-testid='ov-target-select-clear']").trigger("click");
    expect(wrapper.emitted("update:selected")?.at(-1)).toEqual([[]]);

    await wrapper.get("[data-testid='ov-target-search']").setValue("agent");
    expect(wrapper.findAll(".option")).toHaveLength(1);
    await wrapper.get("[data-testid='ov-target-search']").setValue("missing");
    expect(wrapper.text()).toContain("没有匹配的进化对象");
  });

  it("exposes a focus helper that opens the popover", async () => {
    const wrapper = mount(TargetMultiSelect, {
      props: { options, selected: [] },
    });
    (wrapper.vm as unknown as { focus: () => void }).focus();
    await wrapper.vm.$nextTick();
    expect((wrapper.get("details").element as HTMLDetailsElement).open).toBe(true);
  });
});
