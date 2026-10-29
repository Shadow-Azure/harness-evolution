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
      props: {
        id: { type: String, default: "" },
        type: { type: String, default: "" },
        position: { type: String, default: "" },
      },
      setup: (props) => () =>
        h("span", {
          "data-handle-id": props.id,
          "data-handle-position": props.position,
          "data-handle-type": props.type,
        }),
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
                  title: "index read failed",
                  width: 276,
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

    const card = wrapper.get(".rf-finding");
    expect(card.attributes("aria-label")).toBe(
      "问题 case-sel: index read failed",
    );
    expect(card.attributes("title")).toBe("case-select · index read failed");
    expect(card.get(".finding-title").text()).toBe("index read failed");
    expect(wrapper.find(".finding-reason").exists()).toBe(false);
    expect(select).toHaveBeenCalledWith("case-select");
    expect(parentClick).not.toHaveBeenCalled();
  });

  it("renders structural red cards with the measured layout width", () => {
    const wrapper = mount(BadCaseNode, {
      props: {
        data: {
          badCaseId: "case-width",
          shortId: "case-wid",
          title: "a long measured problem title",
          width: 276,
          degraded: false,
          active: false,
        },
      },
      global: {
        provide: {
          [BAD_CASE_SELECT_KEY]: vi.fn(),
        },
      },
    });

    const card = wrapper.get(".rf-finding");
    expect(card.attributes("style")).toContain("width: 276px");
    expect(card.get(".finding-title").text()).toBe(
      "a long measured problem title",
    );
    expect(card.attributes("title")).toBe(
      "case-width · a long measured problem title",
    );
    expect(card.classes().some((name) => name.startsWith("state-"))).toBe(
      false,
    );
  });

  it("exposes source handles for vertical error-card stacking", () => {
    const wrapper = mount(BadCaseNode, {
      props: {
        data: {
          badCaseId: "case-stack",
          shortId: "case-sta",
          title: "stacked problem",
          width: 180,
          degraded: false,
          active: false,
        },
      },
      global: {
        provide: {
          [BAD_CASE_SELECT_KEY]: vi.fn(),
        },
      },
    });

    expect(wrapper.get('[data-handle-id="card-stack-top"]').attributes()).toMatchObject({
      "data-handle-position": "top",
      "data-handle-type": "source",
    });
    expect(wrapper.get('[data-handle-id="card-stack-bottom"]').attributes()).toMatchObject({
      "data-handle-position": "bottom",
      "data-handle-type": "source",
    });
  });
});
