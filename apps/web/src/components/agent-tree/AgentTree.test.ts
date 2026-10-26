// @vitest-environment jsdom
/* eslint-disable vue/one-component-per-file, vue/require-prop-types */

import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { describe, expect, it, vi } from "vitest";

import type { SessionTree } from "@harness/contracts";

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
    Position: {
      Left: "left",
      Right: "right",
      Top: "top",
      Bottom: "bottom",
    },
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
    expect(Number(flow.attributes("data-node-count"))).toBe(4);

    wrapper.getComponent({ name: "VueFlow" }).vm.$emit("node-click", {
      node: {
        id: "main-group",
        type: "collapse",
        data: { parentForCollapse: "main" },
      },
    });
    await wrapper.setProps({ expanded: ["main"] });
    expect(wrapper.emitted("toggle-expanded")).toEqual([["main"]]);
    expect(
      Number(
        wrapper
          .get('[data-testid="vue-flow"]')
          .attributes("data-node-count"),
      ),
    ).toBeGreaterThan(4);
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

  it("keeps layout diagnostics out of the visible user interface", () => {
    const tree = {
      sessionId: "missing-parent-event",
      agents: [
        {
          agentId: "main",
          parentAgentId: null,
          kind: "main",
          agentType: null,
          taskKind: null,
          spawnDepth: 0,
          label: "主会话",
          desc: "主会话",
          lines: 10,
          messagesCount: 10,
          toolUseId: null,
          skillName: null,
          teamName: null,
          events: [],
        },
        {
          agentId: "Agent-without-trigger",
          parentAgentId: "main",
          kind: "subagent",
          agentType: "Explore",
          taskKind: null,
          spawnDepth: 1,
          label: "Explore · 无父事件",
          desc: "缺少父事件",
          lines: 2,
          messagesCount: 2,
          toolUseId: "missing-trigger",
          skillName: null,
          teamName: null,
          events: [],
        },
      ],
      badCases: [],
    } satisfies SessionTree;
    const wrapper = mount(AgentTree, {
      props: { tree, expanded: ["main"] },
    });

    expect(wrapper.find(".diagnostics").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("MISSING_PARENT_EVENT");
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
        .filter(
          (node: { id: string; type: string }) =>
            node.type === "agent" && node.id !== "agent-a",
        )
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
    wrapper.getComponent({ name: "VueFlow" }).vm.$emit("nodes-initialized");
    await nextTick();
    await nextTick();

    expect(setCenterMock).toHaveBeenCalledWith(
      expect.any(Number),
      expect.any(Number),
      expect.objectContaining({ zoom: 0.85, duration: 260 }),
    );
  });

  it("selects a graph problem card without changing Agent selection", async () => {
    setCenterMock.mockClear();
    const wrapper = mount(AgentTree, {
      props: {
        tree: demoNestedTree,
        expanded: ["main", "agent-a"],
      },
    });
    const flow = wrapper.getComponent({ name: "VueFlow" });
    const card = flow.props("nodes").find(
      (node: { type: string }) => node.type === "badcase",
    );
    expect(card).toBeDefined();

    flow.vm.$emit("node-click", { node: card });
    await nextTick();

    expect(wrapper.emitted("badcase-select")).toEqual([
      [card.data.badCaseId],
    ]);
    expect(wrapper.emitted("node-select")).toBeUndefined();
    expect(setCenterMock).toHaveBeenCalledWith(
      expect.any(Number),
      expect.any(Number),
      expect.objectContaining({ zoom: 0.85, duration: 260 }),
    );
  });

  it("keeps exactly one graph problem card active for a selected badCaseId", async () => {
    const wrapper = mount(AgentTree, {
      props: {
        tree: demoNestedTree,
        expanded: ["main", "agent-a"],
        activeBadCaseId: "case-self-agent",
      },
    });
    await nextTick();
    await nextTick();

    const cards = wrapper
      .getComponent({ name: "VueFlow" })
      .props("nodes")
      .filter((node: { type: string }) => node.type === "badcase");
    expect(
      cards.filter(
        (node: { data: { active?: boolean } }) => node.data.active,
      ),
    ).toHaveLength(1);
    expect(
      cards.find(
        (node: {
          data: { active?: boolean; badCaseId: string };
        }) => node.data.active,
      )?.data.badCaseId,
    ).toBe("case-self-agent");
  });

  it("locates a selected problem after its collapsed host expands", async () => {
    setCenterMock.mockClear();
    const foldedTree = {
      ...demoNestedTree,
      badCases: [
        {
          ...demoNestedTree.badCases[0]!,
          badCaseId: "case-folded-host",
          anchor: { agentId: "agent-extra-1", eventIndex: -1 },
        },
      ],
    };
    const wrapper = mount(AgentTree, {
      props: {
        tree: foldedTree,
        expanded: [],
        activeBadCaseId: "case-folded-host",
      },
    });
    await nextTick();
    await nextTick();

    expect(
      wrapper
        .getComponent({ name: "VueFlow" })
        .props("nodes")
        .some(
          (node: { type: string; data: { badCaseId?: string } }) =>
            node.type === "badcase" &&
            node.data.badCaseId === "case-folded-host",
        ),
    ).toBe(false);
    expect(setCenterMock).not.toHaveBeenCalled();

    await wrapper.setProps({ expanded: ["main"] });
    await nextTick();
    await nextTick();
    await (
      wrapper.vm as {
        locateBadCase: (id: string) => Promise<void>;
      }
    ).locateBadCase("case-folded-host");

    const card = wrapper
      .getComponent({ name: "VueFlow" })
      .props("nodes")
      .find(
        (node: { type: string; data: { badCaseId?: string } }) =>
          node.type === "badcase" &&
          node.data.badCaseId === "case-folded-host",
      );
    expect(card?.data.active).toBe(true);
    expect(setCenterMock).toHaveBeenCalledWith(
      card.position.x + card.data.width / 2,
      card.position.y + 15,
      expect.objectContaining({ zoom: 0.85, duration: 260 }),
    );
  });

  it("cancels delayed topology fitting when locating a problem", async () => {
    vi.useFakeTimers();
    try {
      fitViewMock.mockClear();
      setCenterMock.mockClear();
      const wrapper = mount(AgentTree, {
        props: {
          tree: demoNestedTree,
          expanded: [],
        },
      });

      await wrapper.setProps({ expanded: ["main", "agent-a"] });
      await nextTick();
      await (
        wrapper.vm as {
          locateBadCase: (badCaseId: string) => Promise<void>;
        }
      ).locateBadCase("case-self-skill");
      await vi.advanceTimersByTimeAsync(300);
      await nextTick();

      expect(setCenterMock).toHaveBeenCalled();
      expect(fitViewMock).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });
});
