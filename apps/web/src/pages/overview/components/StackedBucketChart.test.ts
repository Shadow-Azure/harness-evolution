// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import StackedBucketChart from "./StackedBucketChart.vue";

const buckets = [
  { bucket: "2026-11-02", label: "11-02", self: 1, discovery: 0, total: 1 },
  { bucket: "2026-11-09", label: "11-09", self: 1, discovery: 1, total: 2 },
  { bucket: "2026-11-16", label: "11-16", self: 0, discovery: 0, total: 0 },
];

function mountChart(overrides: Record<string, unknown> = {}) {
  return mount(StackedBucketChart, {
    props: { buckets, grain: "week", loading: false, error: null, ...overrides },
  });
}

describe("overview stacked bucket chart", () => {
  it("draws one hover target per bucket and skips zero-value bars", () => {
    const wrapper = mountChart();

    expect(wrapper.findAll("[data-testid^='ov-bucket-']")).toHaveLength(3);
    expect(wrapper.findAll("rect.segment.self")).toHaveLength(2);
    expect(wrapper.findAll("rect.segment.discovery")).toHaveLength(1);
    expect(wrapper.find("[data-bucket='2026-11-16']").exists()).toBe(true);
  });

  it("shows a tooltip with both segments and their shares", async () => {
    const wrapper = mountChart();

    await wrapper.get("[data-bucket='2026-11-09']").trigger("mouseenter");
    const tooltip = wrapper.get("[data-testid='ov-tooltip']");
    expect(tooltip.text()).toContain("11-09");
    expect(tooltip.text()).toContain("自身存在问题 1（50%）");
    expect(tooltip.text()).toContain("发现前置步骤问题 1（50%）");
    expect(tooltip.text()).toContain("合计 2");

    await wrapper.get("[data-bucket='2026-11-09']").trigger("mouseleave");
    expect(wrapper.find("[data-testid='ov-tooltip']").exists()).toBe(false);
  });

  it("emits the clicked bucket's inclusive window", async () => {
    const wrapper = mountChart();

    await wrapper.get("[data-bucket='2026-11-02']").trigger("click");

    expect(wrapper.emitted("select-bucket")).toEqual([
      [{ bucket: "2026-11-02", from: "2026-11-02", to: "2026-11-08" }],
    ]);
  });

  it("keeps a monthly bucket inside its own month", async () => {
    const wrapper = mountChart({
      grain: "month",
      buckets: [
        { bucket: "2026-11-01", label: "2026-11", self: 2, discovery: 1, total: 3 },
      ],
    });

    await wrapper.get("[data-bucket='2026-11-01']").trigger("click");
    expect(wrapper.emitted("select-bucket")).toEqual([
      [{ bucket: "2026-11-01", from: "2026-11-01", to: "2026-11-30" }],
    ]);
  });

  it("shows the clearable empty state when nothing matches", async () => {
    const wrapper = mountChart({ buckets: [] });

    expect(wrapper.find("[data-testid='ov-chart-empty']").exists()).toBe(true);
    await wrapper.get("[data-testid='ov-chart-empty-clear']").trigger("click");
    expect(wrapper.emitted("clear-filters")).toHaveLength(1);
  });

  it("renders skeleton, retryable error, and dense hints", async () => {
    const loading = mountChart({ loading: true, buckets: [] });
    expect(loading.find("[data-testid='ov-chart-loading']").exists()).toBe(true);

    const failed = mountChart({ error: new Error("boom"), code: "INTERNAL" });
    expect(failed.find("[data-testid='ov-chart-error']").exists()).toBe(true);
    expect(failed.text()).toContain("INTERNAL");
    await failed.get("button").trigger("click");
    expect(failed.emitted("retry")).toHaveLength(1);
  });

  it("keeps sixty buckets out of dense mode and enters it at sixty-one", () => {
    const series = (count: number) =>
      Array.from({ length: count }, (_, index) => {
        const bucket = new Date(Date.UTC(2026, 0, 1 + index))
          .toISOString()
          .slice(0, 10);
        return {
          bucket,
          label: bucket.slice(5),
          self: 1,
          discovery: 0,
          total: 1,
        };
      });

    const sixty = mountChart({ buckets: series(60) });
    expect(sixty.find("[data-testid='ov-chart-dense-hint']").exists()).toBe(false);

    const sixtyOne = mountChart({ buckets: series(61) });
    expect(sixtyOne.find("[data-testid='ov-chart-dense-hint']").exists()).toBe(
      true,
    );
  });

  it("labels the y axis with integer ticks", () => {
    const wrapper = mountChart();

    const labels = wrapper.findAll(".yaxis span").map((node) => node.text());
    expect(labels.length).toBeGreaterThanOrEqual(2);
    expect(labels.at(0)).toBe("0");
    expect(labels.every((label) => /^\d+$/.test(label))).toBe(true);
  });
});
