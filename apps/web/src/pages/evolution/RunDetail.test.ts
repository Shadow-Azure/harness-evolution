// @vitest-environment jsdom

import type { EvolutionRunCard } from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { createPinia, setActivePinia } from "pinia";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { server } from "../../test/server";
import RunDetail from "./RunDetail.vue";

const wrappers: VueWrapper[] = [];

const run = (overrides: Partial<EvolutionRunCard> = {}): EvolutionRunCard => ({
  runId: "evo-full-1",
  title: "deep-research v2.0.0 自进化",
  mode: "full",
  target: {
    type: "skill",
    name: "deep-research",
    version: "v2.0.0",
  },
  window: {
    from: "2026-08-20",
    to: "2026-09-10",
  },
  models: ["glm-5.3"],
  createdBy: "Ada",
  createdAt: "2026-10-19T18:42:00+08:00",
  status: "preparing",
  error: null,
  stats: {
    sessions: 128,
    probes: 46,
    usedProbes: 28,
    clusters: 2,
    byAttributeType: {
      model: 1,
      prompt: 1,
      error: 0,
      nonIssue: 18,
    },
  },
  progress: {
    unit: 0,
    total: 7,
    percent: 0,
    stageLabel: "第 1/6 步 · 筛选输入中…",
    doneRounds: 0,
    accepted: 0,
  },
  final: null,
  ...overrides,
});

async function mountPage(runId = "evo-full-1") {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/evolution/runs/:runId", component: { template: "<div />" } },
      { path: "/evolution/cluster/:runId", component: { template: "<div />" } },
    ],
  });
  await router.push(`/evolution/runs/${runId}`);
  await router.isReady();
  const wrapper = mount(RunDetail, {
    global: {
      plugins: [
        [
          VueQueryPlugin,
          {
            queryClient: new QueryClient({
              defaultOptions: { queries: { gcTime: 0, retry: false } },
            }),
          },
        ],
        pinia,
        router,
      ],
    },
  });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
});
afterAll(() => server.close());

describe("evolution run detail page", () => {
  it("renders the accepted preparing run from the run list", async () => {
    server.use(
      http.get("/api/evolution/runs", () =>
        HttpResponse.json({ running: [run()], history: [] })),
    );
    const wrapper = await mountPage();

    expect(wrapper.get("h1").text()).toBe("deep-research v2.0.0 自进化");
    expect(wrapper.get("[data-testid='run-status']").text()).toContain("准备中");
    expect(wrapper.get("[data-testid='run-status']").text()).toContain("已受理");
    expect(wrapper.get(".info-panel").text()).toContain(
      "skill:deep-research@v2.0.0",
    );
    expect(wrapper.get(".info-panel").text()).toContain(
      "2026-08-20 ~ 2026-09-10",
    );
    expect(wrapper.get(".info-panel").text()).toContain("glm-5.3");
    expect(wrapper.get(".info-panel").text()).toContain("完整自进化");
    // The full-run landing page has no cluster-preview entry today; cluster_only
    // runs land on the dedicated preview page instead.
    expect(wrapper.find("[data-testid='evolution-cluster-preview']").exists()).toBe(
      false,
    );
    expect(wrapper.findAll("a").some((link) =>
      (link.attributes("href") ?? "").includes("/evolution/cluster/")
    )).toBe(false);
  });

  it("shows a retryable error when the run list request fails", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/evolution/runs", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              { error: { code: "INTERNAL", message: "failed" } },
              { status: 500 },
            )
          : HttpResponse.json({ running: [run()], history: [] });
      }),
    );
    const wrapper = await mountPage();

    expect(wrapper.get(".error-state").attributes("role")).toBe("alert");
    expect(wrapper.get(".error-state").text()).toContain(
      "运行详情读取失败，请重试",
    );
    expect(wrapper.find("[data-testid='run-status']").exists()).toBe(false);

    await wrapper.get(".error-state button").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-testid='run-status']").text()).toContain("准备中");
  });

  it("reports a missing run without offering a retry", async () => {
    server.use(
      http.get("/api/evolution/runs", () =>
        HttpResponse.json({ running: [], history: [] })),
    );
    const wrapper = await mountPage("evo-missing");

    expect(wrapper.text()).toContain("运行不存在或已被删除");
    expect(wrapper.find(".error-state button").exists()).toBe(false);
  });
});
