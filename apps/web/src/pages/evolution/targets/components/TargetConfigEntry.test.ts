// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { RouterLink } from "vue-router";
import { describe, expect, it } from "vitest";

import TargetConfigEntry from "./TargetConfigEntry.vue";

describe("TargetConfigEntry", () => {
  it("links to the target configuration page with an accessible label", () => {
    const wrapper = mount(TargetConfigEntry, {
      global: {
        stubs: {
          RouterLink: {
            props: ["to"],
            template: "<a><slot /></a>",
          },
        },
      },
    });

    const link = wrapper.getComponent(RouterLink);
    expect(link.props("to")).toBe("/evolution/targets");
    expect(wrapper.get("a").attributes("aria-label")).toBe("配置进化对象");
    expect(wrapper.get("a").attributes("title")).toBe("配置进化对象");
    expect(wrapper.text()).toBe("");
  });
});
