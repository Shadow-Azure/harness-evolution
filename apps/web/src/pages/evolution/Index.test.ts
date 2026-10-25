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
        },
      },
    });

    const canvas = wrapper.get(".canvas");
    expect(canvas.attributes("style")).toContain("width: 100%");
    expect(canvas.attributes("style")).toContain("height: 320px");
  });
});
