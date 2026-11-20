// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import { AgentFlowError, AgentFlowLoading } from "./agentFlowPlaceholder";

describe("AgentFlow placeholders", () => {
  it("renders a full-height loading placeholder for the async flow chunk", () => {
    const wrapper = mount(AgentFlowLoading);
    const root = wrapper.get("[data-testid='tree-loading']");
    expect(root.classes()).toContain("tree-loading");
    expect(wrapper.text()).toContain("正在加载 Agent 执行流视图");
  });

  it("announces a failed flow chunk instead of collapsing silently", () => {
    const wrapper = mount(AgentFlowError);
    const root = wrapper.get("[data-testid='tree-load-error']");
    expect(root.attributes("role")).toBe("alert");
    expect(root.classes()).toContain("tree-loading");
    expect(root.text()).toContain("Agent 执行流视图加载失败");
  });
});
