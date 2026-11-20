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
  vi,
} from "vitest";

import { createAppRouter } from "../../router";
import { signInWithWorkspace } from "../../test/auth";
import { server } from "../../test/server";
import EvolutionPage from "./Index.vue";
import RunGroup from "./components/RunGroup.vue";

const workspaceId = "ws-test";
const ws = `/workspaces/${workspaceId}`;
const runsBase = `/api/workspaces/${workspaceId}/evolution/runs`;

const wrappers: VueWrapper[] = [];
let activeRouter: ReturnType<typeof createAppRouter>;

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
  policy: { preset: "default" },
  cacheEnabled: false,
  createdBy: "Administrator",
  createdAt,
  status,
  error: null,
  stats: {
    sessions: 4,
    versionUnresolvedSessions: 1,
    badCases: 3,
    potential: 2,
    attributed: 2,
    reused: 1,
    clusters: 1,
    byCategory: { flow: 0, context: 0, model: 1, prompt: 1, error: 0 },
  },
  progress: {
    unit: 5,
    total: 7,
    percent: 71,
    stageLabel: "第 6/7 步 · 迭代优化 · 第 1/1 轮",
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

async function mountPage(path = `${ws}/evolution`) {
  const pinia = createPinia();
  setActivePinia(pinia);
  signInWithWorkspace({
    id: "user-1",
    username: "admin",
    displayName: "Administrator",
    role: "admin",
    mustChangePassword: false,
  });
  const router = createAppRouter();
  activeRouter = router;
  await router.push(path);
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
      http.get(runsBase, async () => {
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
      http.get(runsBase, () =>
        HttpResponse.json({ running: [], history: [] })),
    );
    const wrapper = await mountPage();

    expect(wrapper.get("h1").text()).toBe("自进化");
    expect(wrapper.get(".page-note").text()).toContain(
      "基于问题报告对 skill / agent",
    );
    expect(wrapper.text()).toContain("当前没有正在执行的自进化");
    expect(wrapper.text()).toContain("暂无历史记录");
    expect(wrapper.find(".target-config-entry").exists()).toBe(true);
    expect(wrapper.find(".canvas").exists()).toBe(false);
  });

  it("opens the launch wizard from the header action", async () => {
    server.use(
      http.get(runsBase, () =>
        HttpResponse.json({ running: [], history: [] })),
      http.get(`/api${ws}/catalogs/targets`, () =>
        HttpResponse.json({ skill: [], agent: [] })),
    );
    const wrapper = await mountPage();

    expect(wrapper.find("[data-testid='launch-wizard']").exists()).toBe(false);
    await wrapper.get("[data-testid='open-launch-wizard']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-testid='launch-wizard']").exists()).toBe(true);
    expect(wrapper.get("[data-testid='wizard-config-empty']").text()).toContain(
      "当前空间还没有启用的进化对象",
    );
  });

  it("opens the wizard with a focus case from the query and clears it on close", async () => {
    server.use(
      http.get(runsBase, () =>
        HttpResponse.json({ running: [], history: [] })),
      http.get(`/api${ws}/catalogs/targets`, () =>
        HttpResponse.json({
          skill: [
            {
              id: "tgt-1",
              name: "deep-research",
              repoUrl: "https://git.example.com/skills.git",
              subDir: "skills/deep-research",
              defaultRef: "v2.0.0",
              versions: ["v2.0.0"],
            },
          ],
          agent: [],
        })),
      http.get(`/api${ws}/evolution/targets/tgt-1/versions`, () =>
        HttpResponse.json({
          versions: ["v2.0.0"],
          defaultRef: "v2.0.0",
        })),
      http.get(`/api${ws}/bad-cases/case-focus`, () =>
        HttpResponse.json({
          badCaseId: "case-focus",
          badCaseType: "self",
          sessionId: "session-1",
          sessionTitle: "session",
          objectName: "deep-research",
          objectType: "skill",
          objectVersion: "v2.0.0",
          title: "focus",
          reason: "focus reason",
          anchor: { agentId: "agent-1", eventIndex: 0, kind: "event" },
          badCaseAgent: { agentId: "agent-1", sessionId: "session-1" },
          analysis: { status: "unanalyzed" },
          degraded: false,
          diagnosticCode: null,
          metaData: null,
        })),
    );
    const wrapper = await mountPage(`${ws}/evolution?case=case-focus`);
    await flushPromises();

    expect(wrapper.find("[data-testid='launch-wizard']").exists()).toBe(true);
    expect(wrapper.get("[data-testid='wizard-focus-case']").text()).toContain(
      "已锁定为关注对象",
    );

    await wrapper.get("[aria-label='关闭向导']").trigger("click");
    await flushPromises();
    expect(activeRouter.currentRoute.value.query.case).toBeUndefined();
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
      http.get(runsBase, () => HttpResponse.json(response)),
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
    expect(wrapper.findComponent(RunGroup).props("workspaceName")).toBe(
      "测试空间",
    );
    const historyCard = wrapper.get(".run-group-history [data-run-id]");
    expect(historyCard.get("[data-testid='run-workspace-chip']").text()).toBe(
      "测试空间",
    );
    expect(historyCard.get("[data-testid='run-policy-chip']").text()).toBe(
      "默认潜在策略",
    );
    expect(historyCard.get("[data-testid='run-cache-chip']").text()).toBe(
      "不复用缓存",
    );
    expect(historyCard.get(".time").text()).toBe("2026-10-25 10:00");
  });

  it("opens an existing run card at its detail route", async () => {
    server.use(
      http.get(runsBase, () =>
        HttpResponse.json({
          running: [run("running-new", "running", "2026-10-27T10:00:00+08:00")],
          history: [],
        })),
    );
    const wrapper = await mountPage();
    const push = vi.spyOn(activeRouter, "push").mockResolvedValue(undefined);

    wrapper.findComponent(RunGroup).vm.$emit(
      "open",
      "/evolution/runs/running-new",
    );
    await flushPromises();

    expect(push).toHaveBeenCalledWith(
      `${ws}/evolution/runs/running-new`,
    );
  });

  it("retries a failed read without replacing the header", async () => {
    let attempts = 0;
    server.use(
      http.get(runsBase, () => {
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
