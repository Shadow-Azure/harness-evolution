// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { readFileSync } from "node:fs";
import { createPinia, setActivePinia } from "pinia";
import { describe, expect, it } from "vitest";

import TopNav from "./components/layout/TopNav.vue";
import { createAppRouter } from "./router";
import { useAuthStore } from "./stores/auth";
import TopNavSource from "./components/layout/TopNav.vue?raw";

const tokensSource = readFileSync("src/styles/tokens.css", "utf8");

const prototypeTokens = {
  "--bg": "#f4f5f7",
  "--bg-panel": "#fafbfc",
  "--bg-card": "#ffffff",
  "--bg-inset": "#f1f3f6",
  "--border": "#e2e5ea",
  "--text": "#212832",
  "--text-dim": "#5a6372",
  "--text-faint": "#9aa2ae",
  "--blue": "#2f6fe0",
  "--green": "#1f9d6b",
  "--orange": "#d97b1c",
  "--red": "#d63c3c",
  "--purple": "#8a55c9",
  "--cyan": "#158a8a",
} as const;

describe("prototype visual system", () => {
  it("ports the prototype light-mode tokens exactly", () => {
    for (const [name, value] of Object.entries(prototypeTokens)) {
      expect(tokensSource).toContain(`${name}: ${value};`);
    }
  });

  it("uses the prototype brand and underline navigation structure", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();
    await router.push("/evolution");
    await router.isReady();

    const wrapper = mount(TopNav, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }], pinia, router],
      },
    });

    expect(wrapper.get(".brand").text()).toContain("Harness Evolution");
    expect(wrapper.text()).not.toContain("Harness Lens");
    expect(wrapper.text()).not.toContain("Vue shell");
    expect(wrapper.findAll("nav .tn-item")).toHaveLength(2);
    expect(wrapper.text()).toContain("Session 错误查看");
    expect(wrapper.text()).toContain("会话轨迹与归因");
    expect(wrapper.text()).toContain("点击 ID 跨页溯源");
    expect(wrapper.text()).not.toContain("Errors");
    expect(wrapper.get("nav .tn-item.active").text()).toContain("自进化");
    expect(TopNavSource).toContain("border-bottom-color: var(--blue)");
    expect(TopNavSource).toContain(".tn-item#tn-evo.active");
  });
});
