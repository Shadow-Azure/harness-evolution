// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import EvolutionPage from "./Index.vue";

describe("evolution page", () => {
  it("sizes the graph container without waiting for scoped CSS", () => {
    const wrapper = mount(EvolutionPage, {
      global: {
        stubs: {
          VueFlow: true,
          RouterLink: {
            props: ["to"],
            template: "<a><slot /></a>",
          },
        },
      },
    });

    const canvas = wrapper.get(".canvas");
    expect(canvas.attributes("style")).toContain("width: 100%");
    expect(canvas.attributes("style")).toContain("height: 320px");
  });

  it("exposes the target configuration entry", () => {
    const wrapper = mount(EvolutionPage, {
      global: {
        stubs: {
          VueFlow: true,
          RouterLink: {
            props: ["to"],
            template: "<a><slot /></a>",
          },
        },
      },
    });

    expect(wrapper.get(".target-config-entry").attributes("aria-label")).toBe(
      "配置进化对象",
    );
  });
});
