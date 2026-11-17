// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { describe, expect, it, vi } from "vitest";

import type { SessionTree } from "@harness/contracts";

import { demoCoreTree } from "./tree/fixtures/demo-nested";

const { fitViewMock } = vi.hoisted(() => ({
  fitViewMock: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@vue-flow/core", async () => {
  const { defineComponent, h } = await import("vue");
  return {
    VueFlow: defineComponent({
      name: "VueFlow",
      props: [
        "nodes",
        "edges",
        "nodesDraggable",
        "nodesConnectable",
        "nodesFocusable",
        "edgesFocusable",
        "minZoom",
        "maxZoom",
      ],
      emits: ["nodes-initialized", "node-click"],
      setup(props, { attrs, slots }) {
        return () =>
          h(
            "div",
            {
              ...attrs,
              "data-testid": "vue-flow",
              "data-node-count": props.nodes?.length ?? 0,
              "data-edge-count": props.edges?.length ?? 0,
            },
            slots.default?.(),
          );
      },
    }),
    Handle: defineComponent({ setup: () => () => h("div") }),
    Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
    useVueFlow: () => ({
      fitView: fitViewMock,
      getViewport: () => ({ x: 0, y: 0, zoom: 0.7 }),
      setCenter: vi.fn(),
      zoomIn: vi.fn(),
      zoomOut: vi.fn(),
    }),
  };
});

vi.mock("@vue-flow/background", async () => {
  const { defineComponent, h } = await import("vue");
  return { Background: defineComponent({ setup: () => () => h("div") }) };
});

vi.mock("@vue-flow/controls", async () => {
  const { defineComponent, h } = await import("vue");
  return {
    ControlButton: defineComponent({
      setup(_, { attrs, slots }) {
        return () => h("button", attrs, slots.default?.());
      },
    }),
  };
});

import AgentFlow from "./AgentFlow.vue";

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
}

describe("AgentFlow", () => {
  it("renders the lane DAG by default and toggles to the structural tree", async () => {
    const wrapper = mount(AgentFlow, {
      props: {
        tree: demoCoreTree,
        activeBadCaseId: "case-discovery",
        expanded: ["main"],
      },
    });
    expect(wrapper.find("[data-testid='lane-dag']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='agent-tree']").exists()).toBe(false);
    expect(wrapper.text()).toContain("全部 lane 展开");

    await wrapper.get("[data-testid='flow-mode-tree']").trigger("click");
    await nextTick();
    expect(wrapper.find("[data-testid='agent-tree']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='lane-dag']").exists()).toBe(false);

    await wrapper.get("[data-testid='flow-mode-dag']").trigger("click");
    await nextTick();
    expect(wrapper.find("[data-testid='lane-dag']").exists()).toBe(true);
    expect(
      wrapper.get("[data-bad-case-id='case-discovery']").classes(),
    ).toContain("is-selected");
    wrapper.unmount();
  });

  it("keeps the selected case while switching views and exposes locate", async () => {
    const wrapper = mount(AgentFlow, {
      props: {
        tree: demoCoreTree,
        activeBadCaseId: "case-self-skill",
      },
    });
    const laneViewport = wrapper.get("[data-testid='lane-viewport']");
    stubViewport(laneViewport.element);
    await nextTick();

    await wrapper.get("[data-testid='flow-mode-tree']").trigger("click");
    await nextTick();
    const tree = wrapper.getComponent({ name: "AgentTree" });
    expect(tree.props("activeBadCaseId")).toBe("case-self-skill");

    await wrapper.get("[data-testid='flow-mode-dag']").trigger("click");
    await nextTick();
    expect(
      wrapper.get("[data-bad-case-id='case-self-skill']").classes(),
    ).toContain("is-selected");

    const newViewport = wrapper.get("[data-testid='lane-viewport']");
    stubViewport(newViewport.element);
    const before = (wrapper.get(".ld-canvas").element as HTMLElement).style.transform;
    (
      wrapper.vm as unknown as { locateBadCase: (id: string) => void }
    ).locateBadCase("case-self-skill");
    await nextTick();
    expect(
      (wrapper.get(".ld-canvas").element as HTMLElement).style.transform,
    ).not.toBe(before);
    wrapper.unmount();
  });

  it("shows the collapse control only in tree mode and forwards it", async () => {
    const wrapper = mount(AgentFlow, {
      props: { tree: demoCoreTree, expanded: ["main"] },
    });
    expect(wrapper.find("[data-testid='collapse-tree']").exists()).toBe(false);
    await wrapper.get("[data-testid='flow-mode-tree']").trigger("click");
    await nextTick();
    await wrapper.get("[data-testid='collapse-tree']").trigger("click");
    expect(wrapper.emitted("collapse-all")).toEqual([[]]);
    wrapper.unmount();
  });

  it("remembers the last selected view in localStorage", async () => {
    const store = new Map<string, string>();
    const storage = {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => store.set(key, value),
      removeItem: (key: string) => store.delete(key),
    };
    vi.stubGlobal("localStorage", storage);
    store.set("he:flow-mode", "tree");
    const wrapper = mount(AgentFlow, {
      props: { tree: demoCoreTree },
    });
    expect(wrapper.find("[data-testid='agent-tree']").exists()).toBe(true);
    await wrapper.get("[data-testid='flow-mode-dag']").trigger("click");
    expect(store.get("he:flow-mode")).toBe("dag");
    vi.unstubAllGlobals();
    wrapper.unmount();
  });

  it("accepts an explicit tree default for the visual fixture", async () => {
    const tree: SessionTree = demoCoreTree;
    const wrapper = mount(AgentFlow, {
      props: { tree, defaultMode: "tree" },
    });
    expect(wrapper.find("[data-testid='agent-tree']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='lane-dag']").exists()).toBe(false);
    wrapper.unmount();
  });
});
