// @vitest-environment jsdom

import type { EvolutionRunCard, EvolutionRunList } from "@harness/contracts";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { delay, http, HttpResponse } from "msw";
import { createPinia, setActivePinia } from "pinia";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
} from "vitest";

import { createAppRouter } from "../../router";
import { server } from "../../test/server";
import EvolutionPage from "./Index.vue";

const wrappers: VueWrapper[] = [];

const run = (
  runId: string,
  status: EvolutionRunCard["status"],
  createdAt: string,
): EvolutionRunCard => ({
  runId,
  title: `${runId} title`,
  mode: "full",
  target: { type: "skill", name: "deep-research", version: "v2.0.0" },
  window: { from: "2026-08-20", to: "2026-09-10" },
  models: ["glm-5.3"],
  createdBy: "Administrator",
  createdAt,
  status,
  error: null,
  stats: {
    sessions: 4,
    probes: 3,
    usedProbes: 2,
    clusters: 1,
    byAttributeType: { model: 1, prompt: 1, error: 0, nonIssue: 1 },
  },
  progress: {
    unit: 4,
    total: 6,
    percent: 67,
    stageLabel: "第 5/6 步 · 迭代优化 · 第 1/1 轮",
    doneRounds: 0,
    accepted: 0,
  },
  final: status === "completed"
    ? {
        bestVersion: "v2.0.1-best",
        branchName: "evo/run",
        pushStatus: "succeeded",
        verdict: true,
        bestScore: 88.9,
        initScore: 84.3,
      }
    : null,
});

async function mountPage() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createAppRouter();
  await router.push("/evolution");
  await router.isReady();
  const wrapper = mount(EvolutionPage, {
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

describe("evolution run list page", () => {
  it("shows the shared loading state while runs are pending", async () => {
    server.use(
      http.get("/api/evolution/runs", async () => {
        await delay(100);
        return HttpResponse.json({ running: [], history: [] });
      }),
    );
    const wrapper = await mountPage();

    expect(wrapper.get("[role='status']").attributes("aria-label")).toBe(
      "正在读取自进化运行",
    );
    expect(wrapper.find("[data-testid='evolution-run-list']").exists()).toBe(
      true,
    );
  });

  it("renders both required empty groups and keeps launch explicitly unavailable", async () => {
    server.use(
      http.get("/api/evolution/runs", () =>
        HttpResponse.json({ running: [], history: [] })),
    );
    const wrapper = await mountPage();

    expect(wrapper.get("h1").text()).toBe("自进化");
    expect(wrapper.get(".page-note").text()).toContain(
      "基于问题报告对 skill / agent",
    );
    expect(wrapper.text()).toContain("当前没有正在执行的自进化");
    expect(wrapper.text()).toContain("暂无历史记录");
    const launch = wrapper.get(".launch-run");
    expect(launch.attributes("disabled")).toBeDefined();
    expect(launch.attributes("title")).toContain("M5-05");
    expect(wrapper.find(".target-config-entry").exists()).toBe(true);
    expect(wrapper.find(".canvas").exists()).toBe(false);
  });

  it("preserves backend group grouping and ordering", async () => {
    const response: EvolutionRunList = {
      running: [
        run("running-new", "running", "2026-10-27T10:00:00+08:00"),
        run("blocked-old", "blocked", "2026-10-26T10:00:00+08:00"),
      ],
      history: [
        run("failed-new", "failed", "2026-10-25T10:00:00+08:00"),
        run("completed-old", "completed", "2026-10-24T10:00:00+08:00"),
      ],
    };
    server.use(
      http.get("/api/evolution/runs", () => HttpResponse.json(response)),
    );
    const wrapper = await mountPage();

    expect(
      wrapper.findAll(".run-group-running [data-run-id]")
        .map((node) => node.attributes("data-run-id")),
    ).toEqual(["running-new", "blocked-old"]);
    expect(
      wrapper.findAll(".run-group-history [data-run-id]")
        .map((node) => node.attributes("data-run-id")),
    ).toEqual(["failed-new", "completed-old"]);
    expect(wrapper.text()).toContain("正在执行（2）");
    expect(wrapper.text()).toContain("历史记录（2）");
  });

  it("retries a failed read without replacing the header", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/evolution/runs", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              { error: { code: "INTERNAL", message: "failed" } },
              { status: 500 },
            )
          : HttpResponse.json({ running: [], history: [] });
      }),
    );
    const wrapper = await mountPage();

    expect(wrapper.get("h1").text()).toBe("自进化");
    expect(wrapper.text()).toContain("自进化运行读取失败，请重试");
    await wrapper.get(".error-state button").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("当前没有正在执行的自进化");
  });
});
