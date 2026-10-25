// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

import { demoNestedTree } from "./fixtures/demo-nested";

vi.mock("@vue-flow/core", async () => {
  const { defineComponent, h } = await import("vue");
  return {
    VueFlow: defineComponent({
      name: "VueFlow",
      props: ["nodes", "edges", "nodesDraggable", "nodesConnectable", "minZoom", "maxZoom"],
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
    useVueFlow: () => ({ fitView: vi.fn() }),
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
    expect(wrapper.get('[aria-label="放大"]').attributes("title")).toBe("放大");
    expect(wrapper.get('[aria-label="缩小"]').attributes("title")).toBe("缩小");
    expect(wrapper.get('[aria-label="适应画布"]').attributes("title")).toBe("适应画布");
  });
});
