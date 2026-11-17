// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import { DEFAULT_OVERVIEW_STATE } from "../overviewUrl";
import TargetsFilterBar from "./TargetsFilterBar.vue";

const options = [
  { id: "target-1", name: "synthetic-review", objectType: "skill" as const },
  { id: "target-2", name: "review-agent", objectType: "agent" as const },
];

function state(overrides = {}) {
  return {
    ...DEFAULT_OVERVIEW_STATE,
    tab: "targets" as const,
    ...overrides,
  };
}

describe("TargetsFilterBar", () => {
  it("emits range, window, grain, target, and clear changes", async () => {
    const wrapper = mount(TargetsFilterBar, {
      props: {
        state: state({ range: 30, targets: ["target-1"] }),
        options,
        window: { from: "2026-10-01", to: "2026-11-16" },
      },
    });

    await wrapper.get("[data-testid='ov-target-range-7']").trigger("click");
    expect(wrapper.emitted("update:range")?.at(-1)).toEqual([7]);

    await wrapper.get("[data-testid='ov-target-grain-day']").trigger("click");
    expect(wrapper.emitted("update:grain")?.at(-1)).toEqual(["day"]);

    await wrapper.get("[data-testid='ov-target-option-target-2']").setValue(true);
    expect(wrapper.emitted("update:targets")?.at(-1)).toEqual([
      ["target-1", "target-2"],
    ]);

    await wrapper.get("[data-testid='ov-target-chip-target-1'] button").trigger("click");
    expect(wrapper.emitted("update:targets")?.at(-1)).toEqual([[]]);

    await wrapper.get("[data-testid='ov-target-clear']").trigger("click");
    expect(wrapper.emitted("clear")).toHaveLength(1);
  });

  it("opens a custom window and only emits an ordered pair", async () => {
    const wrapper = mount(TargetsFilterBar, {
      props: {
        state: state({ range: "custom", from: "2026-10-01", to: "2026-10-31" }),
        options,
      },
    });

    await wrapper.get("[data-testid='ov-target-from']").setValue("2026-10-05");
    expect(wrapper.emitted("update:window")?.at(-1)).toEqual([
      { from: "2026-10-05", to: "2026-10-31" },
    ]);
    await wrapper.setProps({
      state: state({ range: "custom", from: "2026-10-05", to: "2026-10-31" }),
    });
    await wrapper.get("[data-testid='ov-target-to']").setValue("2026-10-01");
    expect(wrapper.emitted("update:window")).toHaveLength(1);
  });
});
