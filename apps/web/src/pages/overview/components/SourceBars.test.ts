// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import SourceBars from "./SourceBars.vue";

function rows(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    object: `object-${index + 1}`,
    total: count - index,
    self: count - index - 1,
    discovery: 1,
    sessions: 1,
  }));
}

function mountBars(overrides: Record<string, unknown> = {}) {
  return mount(SourceBars, {
    props: { sources: rows(3), loading: false, error: null, ...overrides },
  });
}

describe("overview source bars", () => {
  it("renders a split bar per object with its counts", () => {
    const wrapper = mountBars();

    expect(wrapper.findAll("[data-testid='ov-source-bar']")).toHaveLength(3);
    const first = wrapper.get("[data-testid='ov-source-bar']");
    expect(first.text()).toContain("object-1");
    expect(first.text()).toContain("3");
    expect(first.text()).toContain("自身 2 / 前置 1");
  });

  it("folds everything past the top six into a rest row", async () => {
    const wrapper = mountBars({ sources: rows(8) });

    expect(wrapper.findAll("[data-testid='ov-source-bar']")).toHaveLength(6);
    const rest = wrapper.get("[data-testid='ov-source-rest']");
    expect(rest.text()).toContain("其余 2 个来源");
    expect(rest.text()).toContain("3");

    await wrapper.get("[data-testid='ov-source-expand']").trigger("click");
    expect(wrapper.findAll("[data-testid='ov-source-bar']")).toHaveLength(8);
    expect(wrapper.find("[data-testid='ov-source-rest']").exists()).toBe(false);
    expect(wrapper.get("[data-testid='ov-source-expand']").text()).toContain(
      "收起为 top 6",
    );
  });

  it("shows the empty copy without any fabricated rows", () => {
    const wrapper = mountBars({ sources: [] });

    expect(wrapper.find("[data-testid='ov-source-bars-empty']").exists()).toBe(true);
    expect(wrapper.findAll("[data-testid='ov-source-bar']")).toHaveLength(0);
  });

  it("renders independent loading and error states with retry", async () => {
    const loading = mountBars({ loading: true, sources: [] });
    expect(loading.find("[data-testid='ov-source-bars-loading']").exists()).toBe(
      true,
    );

    const failed = mountBars({ error: new Error("boom") });
    expect(failed.find("[data-testid='ov-source-bars-error']").exists()).toBe(true);
    await failed.get("button").trigger("click");
    expect(failed.emitted("retry")).toHaveLength(1);
  });
});
