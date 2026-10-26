// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

vi.mock("@vue-flow/core", async () => {
  const { defineComponent, h } = await import("vue");
  return {
    Handle: defineComponent({ setup: () => () => h("div") }),
    Position: { Bottom: "bottom", Left: "left" },
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
});
