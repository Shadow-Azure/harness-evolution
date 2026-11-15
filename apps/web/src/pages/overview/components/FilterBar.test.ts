// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import { DEFAULT_OVERVIEW_STATE } from "../overviewUrl";
import FilterBar from "./FilterBar.vue";

function mountBar(overrides: Record<string, unknown> = {}) {
  return mount(FilterBar, {
    attachTo: document.body,
    props: {
      state: { ...DEFAULT_OVERVIEW_STATE },
      options: ["deep-research", "workflow"],
      window: { from: "2026-08-19", to: "2026-11-16" },
      grainEffective: "week",
      objectsLoading: false,
      ...overrides,
    },
  });
}

describe("overview filter bar", () => {
  it("emits the quick range and grain choices", async () => {
    const wrapper = mountBar();

    await wrapper.get("[data-testid='ov-range-30']").trigger("click");
    await wrapper.get("[data-testid='ov-grain-day']").trigger("click");
    await wrapper.get("[data-testid='ov-clear']").trigger("click");

    expect(wrapper.emitted("update:range")).toEqual([[30]]);
    expect(wrapper.emitted("update:grain")).toEqual([["day"]]);
    expect(wrapper.emitted("clear")).toHaveLength(1);
  });

  it("shows the effective window and the server grain downgrade", () => {
    const wrapper = mountBar({
      state: { ...DEFAULT_OVERVIEW_STATE, grain: "day" },
      grainEffective: "week",
    });

    expect(wrapper.get("[data-testid='ov-window-label']").text()).toBe(
      "2026-08-19 ~ 2026-11-16",
    );
    expect(wrapper.get("[data-testid='ov-grain-downgraded']").text()).toBe(
      "已按周展示",
    );
  });

  it("renders a custom window with prefilled dates and emits a valid change", async () => {
    const wrapper = mountBar({
      state: {
        ...DEFAULT_OVERVIEW_STATE,
        range: "custom",
        from: "2026-10-01",
        to: "2026-10-31",
      },
    });

    const from = wrapper.get("[data-testid='ov-from']");
    expect((from.element as HTMLInputElement).value).toBe("2026-10-01");
    await from.setValue("2026-10-02");
    await from.trigger("change");
    const emissions = wrapper.emitted("update:window") ?? [];
    expect(emissions.at(-1)).toEqual([
      { from: "2026-10-02", to: "2026-10-31" },
    ]);
  });

  it("keeps an invalid custom boundary out of the URL", async () => {
    const wrapper = mountBar({
      state: {
        ...DEFAULT_OVERVIEW_STATE,
        range: "custom",
        from: "2026-10-01",
        to: "2026-10-31",
      },
    });

    const to = wrapper.get("[data-testid='ov-to']");
    await to.setValue("2026-09-01");
    await to.trigger("change");
    expect(wrapper.emitted("update:window")).toBeUndefined();
  });

  it("renders removable chips for every selected source", async () => {
    const wrapper = mountBar({
      state: {
        ...DEFAULT_OVERVIEW_STATE,
        objects: ["deep-research", "workflow"],
      },
    });

    expect(wrapper.get("[data-testid='ov-chip-deep-research']").text()).toContain(
      "deep-research",
    );
    await wrapper
      .get("[data-testid='ov-chip-deep-research'] button")
      .trigger("click");
    expect(wrapper.emitted("update:objects")?.[0]).toEqual([["workflow"]]);
  });

  it("toggles a source option and clears the whole union", async () => {
    const wrapper = mountBar({
      state: { ...DEFAULT_OVERVIEW_STATE, objects: ["deep-research"] },
    });

    const option = wrapper.get("[data-testid='ov-source-option-workflow']");
    await option.setValue(true);
    expect(wrapper.emitted("update:objects")?.[0]).toEqual([
      ["deep-research", "workflow"],
    ]);

    await wrapper.get("[data-testid='ov-source-option-deep-research']").setValue(false);
    expect(wrapper.emitted("update:objects")?.[1]).toEqual([[]]);

    await wrapper.get("[data-testid='ov-source-clear']").trigger("click");
    expect(wrapper.emitted("update:objects")?.[2]).toEqual([[]]);
  });

  it("selects every option and searches the option list", async () => {
    const wrapper = mountBar({
      state: { ...DEFAULT_OVERVIEW_STATE, objects: ["deep-research"] },
    });

    await wrapper.get("[data-testid='ov-source-all']").trigger("click");
    expect(wrapper.emitted("update:objects")?.[0]).toEqual([
      ["deep-research", "workflow"],
    ]);

    await wrapper.get("[data-testid='ov-source-search']").setValue("work");
    expect(wrapper.find("[data-testid='ov-source-option-workflow']").exists()).toBe(
      true,
    );
    expect(
      wrapper.find("[data-testid='ov-source-option-deep-research']").exists(),
    ).toBe(false);
    await wrapper.get("[data-testid='ov-source-search']").setValue("zzz");
    expect(wrapper.text()).toContain("没有匹配的来源");
  });

  it("opens the source popover from the exposed shortcut", async () => {
    const wrapper = mountBar();
    const details = wrapper.get("[data-testid='ov-source-select']");
    expect(details.attributes("open")).toBeUndefined();

    (wrapper.vm as unknown as { focusSources: () => void }).focusSources();
    await wrapper.vm.$nextTick();

    expect(details.attributes("open")).toBeDefined();
  });
});
