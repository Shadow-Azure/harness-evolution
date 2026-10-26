// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { describe, expect, it, vi } from "vitest";

import { BAD_CASE_SELECT_KEY } from "../interactions";
import BadCaseNode from "./BadCaseNode.vue";

vi.mock("@vue-flow/core", async () => {
  const { defineComponent: defineMockComponent } = await import("vue");
  return {
    Handle: defineMockComponent({
      setup: () => () => h("span"),
    }),
    Position: {
      Left: "left",
      Right: "right",
      Top: "top",
      Bottom: "bottom",
    },
  };
});

describe("BadCaseNode", () => {
  it("uses the AgentTree selection callback instead of relying on event bubbling", async () => {
    const select = vi.fn();
    const parentClick = vi.fn();
    const wrapper = mount(
      defineComponent({
        setup: () => () =>
          h(
            "div",
            { onClick: parentClick },
            [
              h(BadCaseNode, {
                data: {
                  badCaseId: "case-select",
                  shortId: "case-sel",
                  reason: "index read failed",
                  displayState: "analyzed_issue_error",
                  degraded: false,
                  active: false,
                },
              }),
            ],
          ),
      }),
      {
        global: {
          provide: {
            [BAD_CASE_SELECT_KEY]: select,
          },
        },
      },
    );

    await wrapper.get(".rf-finding").trigger("click");

    expect(select).toHaveBeenCalledWith("case-select");
    expect(parentClick).not.toHaveBeenCalled();
  });
});
