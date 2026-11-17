// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { TargetTrendBucket } from "@harness/contracts";

import TargetTrendChart from "./TargetTrendChart.vue";

const buckets: TargetTrendBucket[] = [
  {
    bucket: "2026-10-19",
    label: "10-19",
    attributed: 1,
    nonTarget: 2,
    unanalyzed: 3,
    byTarget: [],
  },
  {
    bucket: "2026-10-26",
    label: "10-26",
    attributed: 0,
    nonTarget: 0,
    unanalyzed: 1,
    byTarget: [],
  },
];

describe("TargetTrendChart", () => {
  it("draws the selected states, exposes a tooltip, and emits bucket clicks", async () => {
    const wrapper = mount(TargetTrendChart, {
      props: { buckets, grain: "week", selectedStates: [] },
    });

    expect(wrapper.find("[data-testid='ov-target-chart']").exists()).toBe(true);
    expect(wrapper.findAll("[data-testid='ov-target-metric-attributed']")).toHaveLength(
      1,
    );
    expect(wrapper.get("[data-testid='ov-target-metric-unanalyzed']").text()).toContain(
      "4",
    );

    await wrapper.get("[data-testid='ov-target-bucket-0']").trigger("mouseenter");
    expect(wrapper.get("[data-testid='ov-target-tooltip']").text()).toContain(
      "10-19",
    );
    await wrapper.get("[data-testid='ov-target-bucket-0']").trigger("click");
    expect(wrapper.emitted("select-bucket")?.at(-1)).toEqual([
      { bucket: "2026-10-19", from: "2026-10-19", to: "2026-10-25" },
    ]);
  });

  it("emits metric and empty-state actions", async () => {
    const wrapper = mount(TargetTrendChart, {
      props: { buckets, grain: "week", selectedStates: ["attributed"] },
    });
    await wrapper.get("[data-testid='ov-target-metric-unanalyzed']").trigger("click");
    expect(wrapper.emitted("toggle-state")?.at(-1)).toEqual(["unanalyzed"]);

    const empty = mount(TargetTrendChart, {
      props: { buckets: [], grain: "week" },
    });
    expect(empty.find("[data-testid='ov-target-chart-empty']").exists()).toBe(true);
    await empty.get("[data-testid='ov-target-chart-empty-clear']").trigger("click");
    expect(empty.emitted("clear-filters")).toHaveLength(1);
  });
});
