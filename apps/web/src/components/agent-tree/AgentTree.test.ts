// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { describe, expect, it, vi } from "vitest";

import { demoNestedTree } from "./fixtures/demo-nested";

const { fitViewMock, setCenterMock } = vi.hoisted(() => ({
  fitViewMock: vi.fn(),
  setCenterMock: vi.fn(),
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
        return () => h("div", {
          ...attrs,
          "data-testid": "vue-flow",
          "data-node-count": props.nodes?.length ?? 0,
          "data-edge-count": props.edges?.length ?? 0,
        }, slots.default?.());
      },
    }),
    Handle: defineComponent({ setup: () => () => h("div") }),
    Position: { Left: "left", Bottom: "bottom" },
    useVueFlow: () => ({
      fitView: fitViewMock,
      getViewport: () => ({ x: 0, y: 0, zoom: 0.7 }),
      setCenter: setCenterMock,
      zoomIn: vi.fn(),
      zoomOut: vi.fn(),
    }),
  };
});

vi.mock("@vue-flow/background", async () => {
  const { defineComponent, h } = await import("vue");
  return {
    Background: defineComponent({ setup: () => () => h("div") }),
  };
});

vi.mock("@vue-flow/controls", async () => {
  const { defineComponent, h } = await import("vue");
  const ControlButton = defineComponent({
    setup(_, { attrs, slots }) {
      return () => h("button", attrs, slots.default?.());
    },
  });
  return {
    ControlButton,
  };
});

import AgentTree from "./AgentTree.vue";

describe("AgentTree", () => {
  it("renders the deterministic tree and expands collapse nodes", async () => {
    const wrapper = mount(AgentTree, {
      props: { tree: demoNestedTree, expanded: [] },
    });
    const flow = wrapper.get('[data-testid="vue-flow"]');
    expect(Number(flow.attributes("data-node-count"))).toBe(2);

    wrapper.getComponent({ name: "VueFlow" }).vm.$emit("node-click", {
      node: {
        id: "main-group",
        type: "collapse",
        data: { parentForCollapse: "main" },
      },
    });
    await wrapper.setProps({ expanded: ["main"] });
    expect(wrapper.emitted("toggle-expanded")).toEqual([["main"]]);
    expect(Number(wrapper.get('[data-testid="vue-flow"]').attributes("data-node-count"))).toBeGreaterThan(
      2,
    );
  });

  it("keeps the canvas non-draggable and accessible", () => {
    const wrapper = mount(AgentTree, {
      props: { tree: demoNestedTree, expanded: ["main"] },
    });
    expect(wrapper.get('[data-testid="agent-tree"]').attributes("aria-label")).toBe(
      "Agent 执行流图",
    );
    expect(wrapper.get('[data-testid="vue-flow"]').attributes()).toMatchObject({
      "data-node-count": expect.any(String),
    });
    expect(wrapper.getComponent({ name: "VueFlow" }).props("nodesDraggable")).toBe(false);
    expect(wrapper.getComponent({ name: "VueFlow" }).props("nodesConnectable")).toBe(false);
    expect(wrapper.getComponent({ name: "VueFlow" }).props("nodesFocusable")).toBe(false);
    expect(wrapper.getComponent({ name: "VueFlow" }).props("edgesFocusable")).toBe(false);
    expect(wrapper.get('[aria-label="放大"]').attributes("title")).toBe("放大");
    expect(wrapper.get('[aria-label="缩小"]').attributes("title")).toBe("缩小");
    expect(wrapper.get('[aria-label="适应画布"]').attributes("title")).toBe("适应画布");
  });

  it("locates a selected Agent through the viewport", () => {
    setCenterMock.mockClear();
    const wrapper = mount(AgentTree, {
      props: { tree: demoNestedTree, expanded: ["main"] },
    });

    wrapper.getComponent({ name: "VueFlow" }).vm.$emit("node-click", {
      node: {
        id: "main",
        type: "agent",
        data: { agentId: "main" },
      },
    });

    expect(wrapper.emitted("node-select")).toEqual([["main"]]);
    expect(setCenterMock).toHaveBeenCalledWith(
      expect.any(Number),
      expect.any(Number),
      expect.objectContaining({ zoom: 0.85, duration: 260 }),
    );
  });

  it("locates and highlights a deep-linked Agent and evidence", async () => {
    setCenterMock.mockClear();
    const wrapper = mount(AgentTree, {
      props: {
        tree: demoNestedTree,
        expanded: ["main"],
        activeAgentId: "agent-a",
        activeEventIndex: 1,
      },
    });
    await nextTick();
    await nextTick();

    expect(setCenterMock).toHaveBeenCalled();
    const flow = wrapper.getComponent({ name: "VueFlow" });
    const activeNode = flow.props("nodes").find(
      (node: { id: string }) => node.id === "agent-a",
    );
    expect(activeNode.data.active).toBe(true);
    expect(activeNode.data.activeEvidence).toBe(1);
    expect(
      flow.props("nodes")
        .filter((node: { id: string }) => node.id !== "agent-a")
        .every(
          (node: { data: { activeEvidence: number | null } }) =>
            node.data.activeEvidence === null,
        ),
    ).toBe(true);
  });

  it("locates a deep-linked Agent after its collapsed ancestors expand", async () => {
    setCenterMock.mockClear();
    const wrapper = mount(AgentTree, {
      props: {
        tree: demoNestedTree,
        expanded: [],
        activeAgentId: "agent-a",
      },
    });
    await nextTick();
    await nextTick();
    expect(setCenterMock).not.toHaveBeenCalled();

    await wrapper.setProps({ expanded: ["main"] });
    await nextTick();
    await nextTick();

    expect(setCenterMock).toHaveBeenCalledWith(
      expect.any(Number),
      expect.any(Number),
      expect.objectContaining({ zoom: 0.85, duration: 260 }),
    );
  });
});
