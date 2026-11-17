// @vitest-environment jsdom

import { mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import { demoNestedTree } from "../tree/fixtures/demo-nested";
import LaneDag from "./LaneDag.vue";
import { buildLaneModel } from "./laneModel";

function stubViewport(element: Element) {
  Object.defineProperty(element, "clientWidth", { value: 900, configurable: true });
  Object.defineProperty(element, "clientHeight", { value: 400, configurable: true });
  element.getBoundingClientRect = () =>
    ({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 900,
      bottom: 400,
      width: 900,
      height: 400,
      toJSON: () => ({}),
    }) as DOMRect;
  const target = element as HTMLElement & {
    setPointerCapture: (id: number) => void;
    hasPointerCapture: (id: number) => boolean;
    releasePointerCapture: (id: number) => void;
  };
  target.setPointerCapture = vi.fn();
  target.hasPointerCapture = vi.fn(() => false);
  target.releasePointerCapture = vi.fn();
}

function transform(wrapper: VueWrapper): string {
  return (
    wrapper.get(".ld-canvas").element as HTMLElement
  ).style.transform;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("LaneDag", () => {
  it("renders one row per lane with A1/A1.1 paths and no fold summary", () => {
    const model = buildLaneModel(demoNestedTree);
    const wrapper = mount(LaneDag, {
      props: { model, selectedCaseId: null },
    });
    stubViewport(wrapper.get("[data-testid='lane-viewport']").element);
    const paths = wrapper
      .findAll(".ld-lane")
      .map((lane) => lane.attributes("data-lane-path"));
    expect(paths).toContain("A1");
    expect(paths).toContain("A1.1");
    expect(paths).toContain("A1.1.1");
    expect(wrapper.findAll(".ld-fold-summary")).toHaveLength(0);
    expect(wrapper.text()).toContain("所有 lane 均已展开");
    wrapper.unmount();
  });

  it("renders BC markers above the main lane and highlights only the selected case", async () => {
    const model = buildLaneModel(demoNestedTree, "case-self-skill");
    const wrapper = mount(LaneDag, {
      props: { model, selectedCaseId: "case-self-skill" },
    });
    stubViewport(wrapper.get("[data-testid='lane-viewport']").element);
    const marker = wrapper.get("[data-bad-case-id='case-self-skill']");
    expect(marker.classes()).toContain("is-selected");
    expect(marker.attributes("aria-pressed")).toBe("true");
    expect(wrapper.get("[data-testid='lane-selected-case']").text()).toContain(
      "高亮 BC",
    );
    expect(wrapper.findAll(".ld-bar.is-case-src").length).toBe(0);
    await wrapper.setProps({ selectedCaseId: "case-discovery" });
    expect(
      wrapper.get("[data-bad-case-id='case-discovery']").classes(),
    ).toContain("is-selected");
    expect(wrapper.findAll(".ld-bar.is-case-src").length).toBe(1);
    wrapper.unmount();
  });

  it("emits case selection when a marker is clicked", async () => {
    const wrapper = mount(LaneDag, {
      props: { model: buildLaneModel(demoNestedTree), selectedCaseId: null },
    });
    stubViewport(wrapper.get("[data-testid='lane-viewport']").element);
    await wrapper.get("[data-bad-case-id='case-discovery']").trigger("click");
    expect(wrapper.emitted("select-case")).toEqual([["case-discovery"]]);
    wrapper.unmount();
  });

  it("zooms with the wheel and exposes fit and 1:1 controls", async () => {
    const wrapper = mount(LaneDag, {
      props: { model: buildLaneModel(demoNestedTree), selectedCaseId: null },
    });
    const viewport = wrapper.get("[data-testid='lane-viewport']");
    stubViewport(viewport.element);
    await wrapper.vm.$nextTick();
    (wrapper.vm as unknown as { fit: () => void }).fit();
    const fitted = transform(wrapper);
    expect(fitted).toContain("scale(");

    viewport.element.dispatchEvent(
      new WheelEvent("wheel", {
        deltaY: -100,
        clientX: 450,
        clientY: 200,
        bubbles: true,
        cancelable: true,
      }),
    );
    await wrapper.vm.$nextTick();
    expect(transform(wrapper)).not.toBe(fitted);

    await wrapper.get("button[aria-label='恢复 1:1']").trigger("click");
    expect(transform(wrapper)).toBe("translate(0px, 0px) scale(1)");

    await wrapper.get("button[aria-label='适应窗口']").trigger("click");
    expect(transform(wrapper)).toContain("scale(");
    wrapper.unmount();
  });

  it("pans on pointer drag and centers a located case", async () => {
    const wrapper = mount(LaneDag, {
      props: { model: buildLaneModel(demoNestedTree), selectedCaseId: null },
    });
    const viewport = wrapper.get("[data-testid='lane-viewport']");
    stubViewport(viewport.element);
    await wrapper.vm.$nextTick();

    await viewport.trigger("pointerdown", {
      button: 0,
      pointerId: 1,
      clientX: 100,
      clientY: 100,
    });
    await viewport.trigger("pointermove", {
      pointerId: 1,
      clientX: 160,
      clientY: 130,
    });
    await viewport.trigger("pointerup", { pointerId: 1 });
    expect(transform(wrapper)).toContain("translate(");
    expect(viewport.classes()).not.toContain("is-panning");

    const before = transform(wrapper);
    (
      wrapper.vm as unknown as { locateBadCase: (id: string) => void }
    ).locateBadCase("case-self-skill");
    await wrapper.vm.$nextTick();
    expect(transform(wrapper)).not.toBe(before);
    wrapper.unmount();
  });

  it("renders a 57-lane session without collapsing any lane", () => {
    const model = buildLaneModel(demoNestedTree);
    const expanded = {
      ...model,
      lanes: Array.from({ length: 57 }, (_, index) => ({
        ...model.lanes[0]!,
        id: `lane-${index}`,
        path: index === 0 ? "A1" : `A1.${index}`,
        depth: index === 0 ? 0 : 1,
        top: index === 0 ? 46 : 46 + 70 + (index - 1) * 44,
      })),
      height: 46 + 70 + 56 * 44,
    };
    const wrapper = mount(LaneDag, { props: { model: expanded } });
    expect(wrapper.findAll(".ld-lane")).toHaveLength(57);
    expect(wrapper.findAll(".ld-fold-summary")).toHaveLength(0);
    expect(wrapper.text()).toContain("不再按数量折叠");
    wrapper.unmount();
  });
});
