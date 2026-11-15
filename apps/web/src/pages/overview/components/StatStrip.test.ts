// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import StatStrip from "./StatStrip.vue";

const totals = {
  badCases: 25,
  self: 16,
  discovery: 9,
  sessions: 10,
  sources: 6,
  quota: 60,
  used: 25,
};

function mountStrip(props: Record<string, unknown> = {}) {
  return mount(StatStrip, {
    props: { totals, loading: false, error: null, ...props },
  });
}

describe("overview stat strip", () => {
  it("renders the six prototype cells from the summary totals", () => {
    const wrapper = mountStrip();

    expect(wrapper.get("[data-testid='ov-stat-badcases']").text()).toContain("25");
    expect(wrapper.get("[data-testid='ov-stat-badcases']").text()).toContain(
      "bad case 总数",
    );
    expect(wrapper.get("[data-testid='ov-stat-self']").text()).toContain("16");
    expect(wrapper.get("[data-testid='ov-stat-discovery']").text()).toContain("9");
    expect(wrapper.get("[data-testid='ov-stat-sessions']").text()).toContain("10");
    expect(wrapper.get("[data-testid='ov-stat-sources']").text()).toContain("6");
    expect(wrapper.get("[data-testid='ov-stat-quota']").text()).toContain("25 / 60");
    expect(wrapper.findAll("[data-testid='ov-statstrip'] .ss")).toHaveLength(6);
  });

  it("marks a nearly exhausted quota", () => {
    const wrapper = mountStrip({ totals: { ...totals, used: 55 } });

    expect(wrapper.get("[data-testid='ov-stat-quota']").classes()).toContain("bad");
  });

  it("shows placeholders while the summary is pending", () => {
    const wrapper = mountStrip({ totals: null, loading: true });

    expect(wrapper.get("[data-testid='ov-statstrip']").attributes("aria-busy")).toBe(
      "true",
    );
    expect(wrapper.get("[data-testid='ov-stat-badcases']").text()).toContain("—");
  });

  it("emits list metrics and the source shortcut", async () => {
    const wrapper = mountStrip();

    await wrapper.get("[data-testid='ov-stat-self']").trigger("click");
    await wrapper.get("[data-testid='ov-stat-discovery']").trigger("click");
    await wrapper.get("[data-testid='ov-stat-sources-focus']").trigger("click");

    expect(wrapper.emitted("select-type")).toEqual([["self"], ["discovery"]]);
    expect(wrapper.emitted("focus-sources")).toHaveLength(1);
  });

  it("replaces the strip with a retryable block error", async () => {
    const wrapper = mountStrip({ error: new Error("boom") });

    expect(wrapper.find("[data-testid='ov-statstrip']").exists()).toBe(false);
    expect(wrapper.text()).toContain("总览统计加载失败");
    await wrapper.get("button").trigger("click");
    expect(wrapper.emitted("retry")).toHaveLength(1);
  });
});
