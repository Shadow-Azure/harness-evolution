// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

vi.mock("@vue-flow/core", async () => {
  const { defineComponent, h } = await import("vue");
  return {
    Handle: defineComponent({
      props: {
        id: { type: String, default: "" },
        type: { type: String, default: "" },
        position: { type: String, default: "" },
        class: { type: String, default: "" },
        style: { type: Object, default: () => ({}) },
      },
      setup(props) {
        return () =>
          h("div", {
            "data-handle-id": props.id,
            "data-handle-position": props.position,
            "data-handle-type": props.type,
            class: props.class,
            style: props.style,
          });
      },
    }),
    Position: { Bottom: "bottom", Left: "left", Right: "right", Top: "top" },
  };
});

import AgentNode from "./AgentNode.vue";
import type { AgentLayoutNodeData } from "../types";

const data: AgentLayoutNodeData = {
  label: "主会话",
  kind: "root",
  w: 160,
  boxW: 160,
  visualW: 160,
  lines: 100,
  desc: "主会话",
  chain: { items: [], offsets: [], width: 0 },
  agentId: "main",
  parentAgentId: null,
  active: true,
};

describe("AgentNode", () => {
  it("renders an accessible selected button with visible keyboard focus semantics", () => {
    const wrapper = mount(AgentNode, { props: { data } });
    const button = wrapper.get("button.rf-agent");

    expect(button.attributes("type")).toBe("button");
    expect(button.attributes("aria-label")).toBe("主会话");
    expect(button.attributes("aria-pressed")).toBe("true");
    expect(button.classes()).toContain("active");
  });

  it("highlights the deep-linked evidence trigger", () => {
    const wrapper = mount(AgentNode, {
      props: {
        data: {
          ...data,
          activeEvidence: 0,
          chain: {
            items: [
              {
                kind: "skill",
                name: "deep-research",
                evIdx: 0,
                line: 20,
                w: 110,
              },
            ],
            offsets: [55],
            width: 110,
          },
        },
      },
    });

    expect(wrapper.get(".rf-cnode.skill").classes()).toContain("evidence");
  });

  it("does not highlight evidence on an inactive Agent", () => {
    const wrapper = mount(AgentNode, {
      props: {
        data: {
          ...data,
          active: false,
          activeEvidence: 0,
          chain: {
            items: [
              {
                kind: "skill",
                name: "deep-research",
                evIdx: 0,
                line: 20,
                w: 110,
              },
            ],
            offsets: [55],
            width: 110,
          },
        },
      },
    });

    expect(wrapper.get(".rf-cnode.skill").classes()).not.toContain("evidence");
  });

  it("renders a top source handle and red stub for each discoverable trigger", () => {
    const wrapper = mount(AgentNode, {
      props: {
        data: {
          ...data,
          chain: {
            items: [
              {
                kind: "skill",
                name: "deep-research",
                evIdx: 0,
                line: 20,
                w: 110,
              },
            ],
            offsets: [55],
            width: 110,
          },
        },
      },
    });

    const handle = wrapper.get('[data-handle-id="rep0"]');
    expect(handle.attributes()).toMatchObject({
      "data-handle-position": "top",
      "data-handle-type": "source",
    });
    expect(wrapper.findAll(".rf-stub-top")).toHaveLength(1);
    expect(wrapper.get(".rf-stub-top").attributes("style")).toContain(
      "left: 66px",
    );
  });
});
