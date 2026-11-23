// @vitest-environment jsdom

import type { EvolutionRunCard } from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { createPinia, setActivePinia } from "pinia";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { queryKeys } from "../../api/queryKeys";

const workspaceId = "ws-test";
const ws = `/workspaces/${workspaceId}`;
const evolutionBase = `/api/workspaces/${workspaceId}/evolution`;
import { server } from "../../test/server";
import { useAuthStore } from "../../stores/auth";
import RunDetail from "./RunDetail.vue";

const wrappers: VueWrapper[] = [];
let activeQueryClient: QueryClient | null = null;

/** Minimal EventSource double that records listeners and allows manual frames. */
class TestEventSource {
  static instances: TestEventSource[] = [];

  readonly listeners = new Map<string, Array<(event: Event) => void>>();
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    TestEventSource.instances.push(this);
  }

  addEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
  ): void {
    const listenerFn =
      typeof listener === "function"
        ? listener
        : (event: Event) => listener.handleEvent(event);
    const bucket = this.listeners.get(type) ?? [];
    bucket.push(listenerFn);
    this.listeners.set(type, bucket);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, data: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  static latest(): TestEventSource {
    const latest = this.instances.at(-1);
    if (!latest) throw new Error("no EventSource was opened");
    return latest;
  }
}

function run(overrides: Partial<EvolutionRunCard> = {}): EvolutionRunCard {
  return {
    runId: "evo-full-1",
    controlState: "running", canPause: false, canResume: false,
    title: "deep-research v2.0.0 自进化",
    mode: "full",
    target: {
      type: "skill",
      name: "deep-research",
      version: "v2.0.0",
      targetRevision:
        "digest:9080a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789ab",
    },
    window: {
      from: "2026-08-20",
      to: "2026-09-10",
    },
    models: ["glm-5.3"],
    policy: { preset: "default" },
    cacheEnabled: false,
    createdBy: "Ada",
    createdAt: "2026-10-19T18:42:00+08:00",
    status: "preparing",
    degraded: false,
    error: null,
    stats: {
      sessions: 128,
      versionUnresolvedSessions: 3,
      badCases: 46,
      potential: 28,
      attributed: 16,
      reused: 9,
      clusters: 2,
      byCategory: {
        flow: 0,
        context: 0,
        model: 6,
        prompt: 5,
        error: 5,
      },
    },
    progress: {
      unit: 0,
      total: 7,
      percent: 0,
      stageLabel: "第 1/7 步 · 选择范围中…",
      doneRounds: 0,
      accepted: 0,
    },
    final: null,
    ...overrides,
  };
}

const rangeStep = {
  key: "range",
  index: 0,
  title: "选择范围",
  status: "active",
  clickable: true,
  detail: "准备中",
  payload: {
    condition: {
      targetType: "skill",
      targetName: "deep-research",
      targetVersion: "v2.0.0",
      from: "2026-08-20",
      to: "2026-09-10",
      policy: { preset: "default" },
      cacheEnabled: true,
      workspaceId: "ws-test",
    },
    stats: { sessions: 128, badCases: 46, potential: 28 },
  },
};

const attributionRows = Array.from({ length: 28 }, (_, index) => {
  const attributed = index < 16;
  return {
    badCaseId: `case-${index + 1}`,
    sessionId: `session-${index + 1}`,
    attributionId: `probe-${index + 1}`,
    category: attributed ? "error" : null,
    description: `结论 ${index + 1}`,
    source: attributed && index < 9 ? "cached" : "fresh",
    confidence: 0.8,
  };
});

const attributionStep = {
  key: "attribution",
  index: 3,
  title: "对象归因",
  status: "done",
  clickable: true,
  detail: "28 条",
  payload: {
    summary: { potential: 28, reused: 9, fresh: 19, nonTarget: 12 },
    rows: attributionRows,
  },
};

const finalStep = {
  key: "final",
  index: 6,
  title: "测试集终评",
  status: "done",
  clickable: true,
  payload: {
    verdict: true,
    bestVersion: "v2.0.1-best",
    bestScore: 88.9,
    initScore: 84.3,
    metrics: [],
    changes: [],
  },
};

const sessionsStep = {
  key: "sessions",
  index: 1,
  title: "Session 关联",
  status: "done",
  clickable: true,
  payload: {
    summary: {
      reported: 9,
      associated: 5,
      skipped: 3,
      versionUnresolved: 1,
      pending: 0,
    },
    rows: [
      {
        sessionId: "session-1",
        title: "研究运行",
        objectTriggerAt: "2026-09-01T09:00:00+08:00",
        badCaseCount: 2,
        potentialCount: 1,
      },
    ],
    total: 5,
    page: 1,
    pageSize: 4,
  },
};

const iterationStep = {
  key: "iteration",
  index: 5,
  title: "迭代优化",
  status: "active",
  clickable: true,
  detail: "第 1/2 轮",
  payload: {
    rounds: [
      {
        roundId: "round-1",
        clusterId: "C1",
        title: "检索索引读取失败",
        category: "error",
        caseCount: 1,
        confidence: 0.82,
        severity: 7.4,
        cases: [
          {
            badCaseId: "bc-1",
            title: "读取越界",
            objectName: "deep-research",
            badCaseType: "self",
            triggerAt: "2026-09-01T10:00:00+08:00",
            createdAt: "2026-09-01T10:05:00+08:00",
          },
        ],
        status: "evaluating",
        candidate: {
          ref: "evo/run/candidate/r1",
          commit: "abc123",
          message: "candidate",
        },
        patch: {
          files: [
            {
              file: "SKILL.md",
              lines: [
                "@@ -1 +1 @@",
                "- 读取索引",
                "+ 读取索引前校验快照",
              ],
              overwrite: false,
            },
          ],
        },
        push: { status: "succeeded", attempts: 1, error: null },
        eval: {
          status: "evaluating",
          current: 84.6,
          candidate: null,
          nextPollAt: "2026-10-27T12:05:00+08:00",
        },
        accepted: false,
        finalCommit: null,
      },
    ],
  },
};

function detailSteps(
  statuses: Array<"done" | "active" | "pending">,
) {
  const steps = [
    ["range", "选择范围"],
    ["sessions", "Session 关联"],
    ["potential", "潜在 bad case"],
    ["attribution", "对象归因"],
    ["clusters", "聚类与严重度"],
    ["iteration", "迭代优化"],
    ["final", "测试集终评"],
  ] as const;
  return steps.map(([key, title], index) => ({
    index,
    key,
    title,
    status: statuses[index] ?? "pending",
    clickable: statuses[index] !== "pending",
    detail:
      key === "iteration" && statuses[index] === "active"
        ? "第 1/2 轮"
        : null,
  }));
}

/** Blocked-state facts that live directly on the detail shell. */
interface DetailOverrides {
  blockedStage?: "patch" | "push" | "eval" | "attribution" | null;
  retryAttempts?: number;
  nextRetryAt?: string | null;
  evalStatus?: "pending" | "evaluating" | "completed" | "failed" | "timeout";
  lastEventSeq?: number;
}

function detail(
  card = run(),
  statuses: Array<"done" | "active" | "pending"> = [
    "active",
    "pending",
    "pending",
    "pending",
    "pending",
    "pending",
  ],
  overrides: DetailOverrides = {},
) {
  return {
    ...card,
    blockedStage: card.status === "blocked" ? "eval" : null,
    retryAttempts: card.status === "blocked" ? 1 : 0,
    nextRetryAt: null,
    evalStatus: card.status === "blocked" ? "failed" : "pending",
    workspace: {
      repoUrl: "https://example.invalid/skills.git",
      pushRepoUrl: "https://example.invalid/fork/skills.git",
      subDir: "skills/deep-research",
      repoPath: "data/repos/target",
      baseRef: "v2.0.0",
      baseCommit: "9f3c2a1",
      branchName: "evo/evo-full-1",
      workspacePath: "data/workspaces/evo-full-1",
      remote: "origin",
      pushStatus: "succeeded",
      pushedAt: "2026-10-27T12:00:00+08:00",
      pushError: null,
    },
    attributionSkill: {
      key: "root-cause-agent",
      revision: 2,
      contentHash: "b".repeat(64),
      engine: "agent-skill-stub-v1",
    },
    lastEventSeq: 0,
    steps: detailSteps(statuses),
    ...overrides,
  };
}

async function mountPage(runId = "evo-full-1", query = "") {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().setWorkspaceSession({
    user: {
      id: "user-1",
      username: "admin",
      displayName: "Admin",
      role: "admin",
      mustChangePassword: false,
    },
    workspaces: [
      {
        id: workspaceId,
        name: "测试工作空间",
        mark: "测",
        role: "global_admin",
        used: 0,
        quota: 1000,
        memberCount: 1,
        spaceAdminCount: 1,
      },
    ],
    truncated: false,
  });
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/workspaces/:wid/evolution", component: { template: "<div />" } },
      { path: "/workspaces/:wid/evolution/runs/:runId", component: RunDetail },
      {
        path: "/workspaces/:wid/evolution/cluster/:runId",
        component: { template: "<div />" },
      },
      {
        path: "/workspaces/:wid/sessions/:sessionId/errors",
        component: { template: "<div />" },
      },
    ],
  });
  await router.push(`${ws}/evolution/runs/${runId}${query}`);
  await router.isReady();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { gcTime: 0, retry: false } },
  });
  activeQueryClient = queryClient;
  const wrapper = mount(RunDetail, {
    global: {
      plugins: [
        [VueQueryPlugin, { queryClient }],
        pinia,
        router,
      ],
    },
  });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
}

beforeAll(() => {
  vi.stubGlobal("EventSource", TestEventSource);
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
  TestEventSource.instances = [];
});
afterAll(() => {
  server.close();
  vi.unstubAllGlobals();
});

describe("evolution run detail page", () => {
  it("pauses and continues the existing run through the workspace API without losing reached steps", async () => {
    let snapshot = detail(run({ status: "running", canPause: true }));
    let resumes = 0;
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () => HttpResponse.json(snapshot)),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () => HttpResponse.json(iterationStep)),
      http.post(`${evolutionBase}/runs/:runId/pause`, () => {
        snapshot = { ...snapshot, controlState: "paused", canPause: false, canResume: true };
        return HttpResponse.json(snapshot, { status: 202 });
      }),
      http.post(`${evolutionBase}/runs/:runId/resume`, () => {
        resumes++;
        snapshot = { ...snapshot, controlState: "running", canPause: true, canResume: false };
        return HttpResponse.json(snapshot);
      }),
    );
    const wrapper = await mountPage();
    expect(wrapper.get(".control-button").text()).toBe("暂停");
    await wrapper.get(".control-button").trigger("click");
    await flushPromises();
    expect(wrapper.get(".detail-head .badge").text()).toBe("已暂停");
    expect(wrapper.find(".stepper .pulse").exists()).toBe(false);
    expect(wrapper.find('[data-step-key="iteration"]').exists()).toBe(true);
    expect(wrapper.get(".control-button").text()).toBe("继续执行");
    await wrapper.get(".control-button").trigger("click");
    await flushPromises();
    expect(resumes).toBe(1);
    expect(wrapper.get(".detail-head .badge").text()).toBe("正在执行");
    expect(snapshot.runId).toBe("evo-full-1");
  });

  it("shows an unreached explanation when a failed run stops before step 1", async () => {
    const requested: string[] = [];
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "failed",
              error: {
                stage: "prepare",
                message: "仓库 clone 失败",
                at: "2026-10-27T12:00:00+08:00",
              },
              progress: {
                unit: 0,
                total: 7,
                percent: 0,
                stageLabel: "准备运行",
                doneRounds: 0,
                accepted: 0,
              },
            }),
            ["pending", "pending", "pending", "pending", "pending", "pending", "pending"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, ({ params }) => {
        requested.push(String(params.step));
        return HttpResponse.json(rangeStep);
      }),
    );
    const wrapper = await mountPage();

    expect(requested).toEqual([]);
    expect(wrapper.text()).not.toContain("正在读取当前步骤");
    expect(wrapper.text()).toContain("该步骤尚未到达");
    expect(wrapper.text()).toContain("运行在第 1 步完成前已终止");
  });

  it("copies the run branch name from a keyboard-accessible control", async () => {
    const writes: string[] = [];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (value: string) => writes.push(value) },
    });
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(detail())),
      http.get(`${evolutionBase}/runs/evo-full-1/steps/range`, () =>
        HttpResponse.json(rangeStep)),
    );
    const wrapper = await mountPage();

    const button = wrapper.get("[data-testid='copy-branch']");
    expect(button.element.tagName).toBe("BUTTON");
    await button.trigger("click");
    await flushPromises();

    expect(writes).toEqual(["evo/evo-full-1"]);
    expect(button.text()).toContain("已复制");
  });

  it("renders the preparing range step and requests no unreached step", async () => {
    const requested: string[] = [];
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(detail())),
      http.get(`${evolutionBase}/runs/evo-full-1/steps/:step`, ({ params }) => {
        requested.push(String(params.step));
        return HttpResponse.json(rangeStep);
      }),
    );
    const wrapper = await mountPage();

    expect(wrapper.get("h1").text()).toBe("deep-research v2.0.0 自进化");
    expect(wrapper.findAll("[data-step-key]")).toHaveLength(7);
    expect(wrapper.get("[data-step-key='range']").attributes("aria-current")).toBe(
      "step",
    );
    expect(requested).toEqual(["range"]);
    expect(wrapper.get("[data-step-key='clusters']").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-step-key='clusters']").attributes("title")).toBe(
      "该步骤尚未到达",
    );
    expect(wrapper.text()).toContain("准备中");
    expect(wrapper.text()).toContain("evo/evo-full-1");
    expect(wrapper.get("[data-testid='run-workspace-badge']").text()).toBe(
      "测试工作空间",
    );
    expect(wrapper.text()).toContain("默认策略");
    expect(wrapper.text()).toContain("复用缓存归因");
    expect(wrapper.text()).toContain("潜在 bad case");
    expect(wrapper.get("[data-testid='run-attribution-skill']").text()).toContain(
      "root-cause-agent@r2",
    );
    expect(wrapper.text()).toContain("可归因 / 非该对象");
    expect(wrapper.text()).not.toContain("模型（多选）");
    expect(wrapper.find(".workspace-panel").exists()).toBe(false);
    expect(wrapper.find("[data-testid='steps-tab']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='logs-tab']").exists()).toBe(true);
    expect(wrapper.get("[data-testid='run-target-revision']").text()).toBe(
      run().target.targetRevision,
    );
    expect(wrapper.get("[data-testid='step-target-revision']").text()).toBe(
      run().target.targetRevision,
    );
    expect(wrapper.find("[data-testid='evolution-cluster-preview']").exists()).toBe(
      false,
    );
  });

  it("shows prototype goal-and-input facts and folds workspace into the same card", async () => {
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({ status: "completed" }),
            ["done", "done", "done", "done", "done", "done", "done"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/range`, () =>
        HttpResponse.json(rangeStep)),
      http.get(`${evolutionBase}/runs/:runId/steps/attribution`, () =>
        HttpResponse.json(attributionStep)),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(finalStep)),
    );
    const wrapper = await mountPage();

    const info = wrapper.get("[data-testid='run-info-panel']");
    expect(wrapper.get("[data-testid='run-workspace-badge']").text()).toBe(
      "测试工作空间",
    );
    expect(info.text()).toContain("工作空间");
    expect(info.text()).toContain("测试工作空间");
    expect(info.text()).toContain("可归因 / 非该对象");
    expect(info.text()).toContain("16 / 12");
    expect(info.text()).toContain("潜在 bad case 的归因结论分布（28 条）");
    expect(info.text()).toContain("非该对象 12");
    expect(info.text()).toContain("＝ 归因 16 · 复用缓存 9 · 本次新增 7");
    expect(info.text()).toContain("默认策略");
    expect(info.text()).toContain("复用缓存归因");
    expect(info.text()).not.toContain("模型（多选）");
    expect(wrapper.find(".workspace-panel").exists()).toBe(false);
    const workspace = info.get("[data-testid='run-workspace']");
    expect(workspace.element instanceof HTMLDetailsElement).toBe(true);
    expect((workspace.element as HTMLDetailsElement).open).toBe(false);
    expect(info.find("[data-testid='copy-branch']").exists()).toBe(true);
    expect(workspace.text()).toContain("推送目标");
    expect(workspace.get("[data-testid='run-push-repo']").text()).toBe(
      "https://example.invalid/fork/skills.git",
    );

    const html = wrapper.html();
    expect(html.indexOf('data-testid="run-info-panel"')).toBeLessThan(
      html.indexOf('data-testid="run-progress"'),
    );
    expect(wrapper.get("[data-testid='steps-tab']").attributes("aria-selected")).toBe(
      "true",
    );
  });

  it("does not invent a revision for a historical run without one", async () => {
    const historical = run({
      target: { ...run().target, targetRevision: null },
    });
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(detail(historical))),
      http.get(`${evolutionBase}/runs/evo-full-1/steps/range`, () =>
        HttpResponse.json(rangeStep)),
    );
    const wrapper = await mountPage();

    expect(
      wrapper.get("[data-testid='run-target-revision-missing']").text(),
    ).toContain("历史运行未记录 revision");
    expect(
      wrapper.get("[data-testid='step-target-revision-missing']").text(),
    ).toContain("历史运行未记录 revision");
    expect(wrapper.text()).not.toContain("digest:");
  });

  it("loads the info steps and only the active iteration step", async () => {
    const requested: string[] = [];
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "running",
              progress: {
                unit: 4,
                total: 7,
                percent: 67,
                stageLabel: "第 6/7 步 · 迭代优化 · 第 1/2 轮",
                doneRounds: 0,
                accepted: 0,
              },
            }),
            ["done", "done", "done", "done", "done", "active", "pending"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, ({ params }) => {
        requested.push(String(params.step));
        return HttpResponse.json(iterationStep);
      }),
    );
    const wrapper = await mountPage();

    expect(requested).toEqual(["range", "attribution", "iteration"]);
    expect(wrapper.get("[data-step-key='iteration']").attributes("aria-current")).toBe(
      "step",
    );
    expect(wrapper.text()).toContain("检索索引读取失败");
    expect(wrapper.text()).toContain("candidate 已 push");
    expect(wrapper.text()).toContain("evo/run/candidate/r1");
    expect(wrapper.text()).toContain("评测中");
    expect(wrapper.get("[data-step-key='final']").attributes("disabled")).toBeDefined();
  });

  it("switches reached steps through the query-string route", async () => {
    const requested: string[] = [];
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "running",
              progress: {
                unit: 4,
                total: 7,
                percent: 67,
                stageLabel: "第 6/7 步 · 迭代优化 · 第 1/2 轮",
                doneRounds: 0,
                accepted: 0,
              },
            }),
            ["done", "done", "done", "done", "done", "active", "pending"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, ({ params }) => {
        const key = String(params.step);
        requested.push(key);
        if (key === "iteration") return HttpResponse.json(iterationStep);
        return HttpResponse.json({
          key: "clusters",
          index: 4,
          title: "聚类与严重度",
          status: "done",
          clickable: true,
          payload: {
            clusters: [
              {
                clusterId: "C1",
                title: "检索索引读取失败",
                description: "读取越界",
                category: "error",
                caseCount: 1,
                cases: [],
                confidence: 0.82,
                severity: 7.4,
                rank: 1,
              },
            ],
          },
        });
      }),
    );
    const wrapper = await mountPage();

    await wrapper.get("[data-step-key='clusters']").trigger("click");
    await flushPromises();

    expect(wrapper.vm.$route.fullPath).toBe(
      `${ws}/evolution/runs/evo-full-1?step=clusters`,
    );
    expect(requested).toEqual([
      "range",
      "attribution",
      "iteration",
      "clusters",
    ]);
    expect(wrapper.get("[data-step-key='clusters']").attributes("aria-current")).toBe(
      "step",
    );
    expect(wrapper.text()).toContain("聚类与严重度");
  });

  it("requests the default Session page size and pages through the step", async () => {
    const requested: { step: string; query: string }[] = [];
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({ status: "running" }),
            ["done", "done", "pending", "pending", "pending", "pending", "pending"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, ({ params, request }) => {
        const url = new URL(request.url);
        requested.push({
          step: String(params.step),
          query: url.search,
        });
        const page = Number(url.searchParams.get("page") ?? "1");
        return HttpResponse.json({
          ...sessionsStep,
          payload: { ...sessionsStep.payload, page },
        });
      }),
    );
    const wrapper = await mountPage("evo-full-1", "?step=sessions");

    expect(requested).toEqual([
      { step: "range", query: "" },
      { step: "sessions", query: "?page=1&pageSize=4" },
    ]);
    expect(wrapper.text()).toContain("研究运行");

    await wrapper.findAll(".pager button")[1]?.trigger("click");
    await flushPromises();

    expect(requested.at(-1)).toEqual({
      step: "sessions",
      query: "?page=2&pageSize=4",
    });
  });

  it("renders the short Session label with the full title on hover", async () => {
    const longTitle = "SWE-bench astropy-12907 修复任务 ".repeat(120).trim();
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({ status: "running" }),
            ["done", "done", "pending", "pending", "pending", "pending", "pending"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json({
          ...sessionsStep,
          payload: {
            ...sessionsStep.payload,
            rows: [
              {
                sessionId: "session-long",
                title: longTitle,
                short: "SWE-bench astropy-12907",
                objectTriggerAt: "2026-09-01T09:00:00+08:00",
                badCaseCount: 2,
                potentialCount: 1,
              },
            ],
          },
        })),
    );
    const wrapper = await mountPage("evo-full-1", "?step=sessions");

    const title = wrapper.get(".session-title");
    expect(title.text()).toBe("SWE-bench astropy-12907");
    expect(title.attributes("title")).toBe(longTitle);
    expect(wrapper.find(".session-cell").exists()).toBe(true);
    expect(wrapper.findAll(".rep thead th")).toHaveLength(4);
    expect(wrapper.text()).toContain("session-long");
  });

  it("removes a missing cluster deep-link while retaining the notice", async () => {
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({ status: "completed" }),
            ["done", "done", "done", "done", "done", "done", "done"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json({
          key: "clusters",
          index: 4,
          title: "聚类与严重度",
          status: "done",
          clickable: true,
          payload: {
            clusters: [
              {
                clusterId: "C1",
                title: "检索索引读取失败",
                description: "读取越界",
                category: "error",
                caseCount: 1,
                cases: [],
                confidence: 0.82,
                severity: 7.4,
                rank: 1,
              },
            ],
          },
        })),
    );
    const wrapper = await mountPage(
      "evo-full-1",
      "?step=clusters&cluster=missing",
    );

    expect(wrapper.vm.$route.fullPath).toBe(
      `${ws}/evolution/runs/evo-full-1?step=clusters`,
    );
    expect(wrapper.text()).toContain("目标簇已不存在");
  });

  it("loads a completed run's final verdict by default", async () => {
    const requested: string[] = [];
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "completed",
              progress: {
                unit: 6,
                total: 7,
                percent: 100,
                stageLabel: "第 7/7 步 · 测试集终评中…",
                doneRounds: 2,
                accepted: 1,
              },
              final: {
                bestVersion: "v2.0.1-best",
                branchName: "evo/run",
                pushStatus: "succeeded",
                verdict: true,
                bestScore: 88.9,
                initScore: 84.3,
              },
            }),
            ["done", "done", "done", "done", "done", "done", "done"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, ({ params }) => {
        requested.push(String(params.step));
        return HttpResponse.json({
          key: "final",
          index: 6,
          title: "测试集终评",
          status: "done",
          clickable: true,
          payload: {
            verdict: true,
            bestVersion: "v2.0.1-best",
            bestScore: 88.9,
            initScore: 84.3,
            metrics: [
              { name: "任务完成率", init: 78, best: 84, delta: 6, unit: "%" },
            ],
            changes: [
              {
                commit: "cd34ab",
                clusterId: "C1",
                title: "检索索引读取失败",
                category: "error",
                reportCount: 1,
              },
            ],
          },
        });
      }),
    );
    const wrapper = await mountPage();

    expect(requested).toEqual(["range", "attribution", "final"]);
    expect(wrapper.text()).toContain("✓ 自进化有效");
    expect(wrapper.text()).toContain("任务完成率");
    expect(wrapper.text()).toContain("cd34ab");
    expect(wrapper.get("[data-step-key='final']").attributes("aria-current")).toBe(
      "step",
    );
  });

  it("shows blocked facts, the next retry time, and a manual retry action", async () => {
    const nextRetryAt = new Date(2026, 9, 27, 12, 5, 0).toISOString();
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "blocked",
              error: {
                stage: "eval",
                message: "评测执行失败：sandbox timeout",
                at: "2026-10-27T12:00:00+08:00",
              },
              stats: {
                sessions: 128,
                versionUnresolvedSessions: 3,
                badCases: 46,
                potential: 28,
                attributed: 16,
                reused: 9,
                clusters: 1,
                byCategory: {
                  flow: 0,
                  context: 0,
                  model: 6,
                  prompt: 5,
                  error: 5,
                },
              },
              progress: {
                unit: 4,
                total: 7,
                percent: 80,
                stageLabel: "第 6/7 步 · 迭代优化 · 第 1/1 轮",
                doneRounds: 0,
                accepted: 0,
              },
            }),
            ["done", "done", "done", "done", "done", "active", "pending"],
            {
              blockedStage: "eval",
              retryAttempts: 1,
              nextRetryAt,
            },
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json({
          ...iterationStep,
          detail: "第 1/1 轮",
          payload: {
            rounds: [
              {
                ...iterationStep.payload.rounds[0],
                status: "evaluating",
                candidate: null,
                patch: null,
                push: { status: "succeeded", attempts: 1, error: null },
                eval: {
                  status: "failed",
                  current: 84.6,
                  candidate: null,
                  nextPollAt: null,
                },
              },
            ],
          },
        })),
    );
    const wrapper = await mountPage();
    const banner = wrapper.get("[data-testid='blocked-banner']");

    expect(banner.text()).toContain("评测执行失败：sandbox timeout");
    expect(banner.text()).toContain("运行在评测（eval）阶段阻塞");
    expect(banner.text()).toContain("自动重试 1 次");
    expect(wrapper.get("[data-testid='next-retry-at']").text()).toContain(
      "2026-10-27 12:05:00",
    );
    expect(wrapper.get("[data-testid='run-retry']").text()).toBe("重试");
    expect(wrapper.text()).toContain("评测失败");
    expect(wrapper.text()).toContain("查看执行日志");
  });

  it("refreshes pending, classified and non-target counts while fresh reports arrive", async () => {
    let count = 0;
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () => HttpResponse.json(detail(
        run(), ["done", "done", "done", "active", "pending", "pending", "pending"],
      ))),
      http.get(`${evolutionBase}/runs/:runId/steps/range`, () => HttpResponse.json(rangeStep)),
      http.get(`${evolutionBase}/runs/:runId/attribution-jobs`, () => HttpResponse.json({ items: [] })),
      http.get(`${evolutionBase}/runs/:runId/steps/attribution`, () => HttpResponse.json({
        ...attributionStep,
        status: "active",
        payload: {
          summary: { potential: 8, reused: 0, fresh: count, nonTarget: count ? 1 : 0 },
          rows: attributionRows.slice(0, count).map((row, index) => ({
            ...row, category: index < 2 ? null : "flow", source: "fresh",
            conclusion: ["non_target", "inconclusive"][index] ?? "attributed",
          })),
        },
      })),
    );
    const wrapper = await mountPage();
    const info = wrapper.get("[data-testid='run-info-panel']");
    expect(info.text()).toContain("未归因 8");
    expect(wrapper.text()).toContain("当前还没有归因报告");

    // Refresh only the run shell, as the REST fallback does when SSE drops.
    count = 4;
    await activeQueryClient!.refetchQueries({
      queryKey: queryKeys.evolutionRun(workspaceId, "evo-full-1"), exact: true,
    });
    await vi.waitFor(() => expect(info.text()).toContain("未归因 4"));
    expect(info.text()).toContain("流程 2");
    expect(info.text()).toContain("证据不足 1");
    expect(wrapper.get(".type-inconclusive").text()).toBe("证据不足");
    expect(info.text()).toContain("非该对象 1");
    expect(info.text()).toContain("＝ 归因 2 · 复用缓存 0 · 本次新增 2");
    expect(wrapper.get(".wz-stats").text()).toContain("8潜在 bad case4已出报告");
    expect(wrapper.findAll("tbody tr")).toHaveLength(4);
  });

  it("labels blocked attribution and exposes both automatic and manual retry", async () => {
    const nextRetryAt = new Date(2026, 9, 27, 12, 5, 0).toISOString();
    server.use(
      http.get(`${evolutionBase}/runs/:runId/attribution-jobs`, () =>
        new HttpResponse(null, { status: 503 })),
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "blocked",
              error: {
                stage: "attribution",
                message: "归因引擎暂时不可用",
                at: "2026-10-27T12:00:00+08:00",
              },
              progress: {
                unit: 3,
                total: 6,
                percent: 50,
                stageLabel: "第 4/6 步 · 对象归因",
                doneRounds: 0,
                accepted: 0,
              },
            }),
            ["done", "done", "done", "active", "pending", "pending", "pending"],
            {
              blockedStage: "attribution",
              retryAttempts: 2,
              nextRetryAt,
            },
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/range`, () =>
        HttpResponse.json(rangeStep)),
      http.get(`${evolutionBase}/runs/:runId/steps/attribution`, () =>
        HttpResponse.json({
          key: "attribution",
          index: 3,
          title: "对象归因",
          status: "active",
          clickable: true,
          detail: "0 条",
          payload: {
            summary: {
              potential: 28,
              reused: 0,
              fresh: 0,
              nonTarget: 0,
            },
            rows: [],
          },
        })),
    );
    const wrapper = await mountPage();
    const banner = wrapper.get("[data-testid='blocked-banner']");

    expect(wrapper.get("[data-step-key='attribution']").attributes("aria-current")).toBe(
      "step",
    );
    expect(banner.text()).toContain("运行在归因（attribution）阶段阻塞");
    expect(banner.text()).toContain("归因引擎暂时不可用");
    expect(banner.text()).toContain("自动重试 2 次");
    expect(wrapper.get("[data-testid='next-retry-at']").text()).toContain(
      "等待自动重试",
    );
    expect(wrapper.get("[data-testid='run-retry']").text()).toBe("重试");
    expect(wrapper.get("[data-step-key='clusters']").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("当前还没有归因报告");
    expect(wrapper.text()).toContain("归因任务进度读取失败");
    expect(wrapper.text()).not.toContain("当前没有归因执行记录");
    expect(wrapper.text()).toContain("0 / 0");
    expect(wrapper.text()).toContain("未归因 28");
  });

  it("derives attributed and non-target counts from attribution rows for legacy runs", async () => {
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "completed",
              stats: {
                sessions: 5,
                versionUnresolvedSessions: 0,
                badCases: 3,
                potential: 3,
                attributed: 3,
                reused: 0,
                clusters: 0,
                byCategory: { model: 0, prompt: 0, error: 2, flow: 0, context: 0 },
              },
            }),
            ["done", "done", "done", "done", "done", "done", "done"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/range`, () =>
        HttpResponse.json(rangeStep)),
      http.get(`${evolutionBase}/runs/:runId/steps/attribution`, () =>
        HttpResponse.json({
          key: "attribution",
          index: 3,
          title: "对象归因",
          status: "done",
          clickable: true,
          payload: {
            summary: { potential: 3, reused: 0, fresh: 3, nonTarget: 1 },
            rows: [
              {
                badCaseId: "legacy-case-1",
                sessionId: "legacy-session-1",
                attributionId: "legacy-probe-1",
                category: "error",
                description: "归因结论",
                source: "fresh",
                confidence: 0.8,
              },
              {
                badCaseId: "legacy-case-2",
                sessionId: "legacy-session-2",
                attributionId: "legacy-probe-2",
                category: "error",
                description: "归因结论",
                source: "fresh",
                confidence: 0.8,
              },
              {
                badCaseId: "legacy-case-3",
                sessionId: "legacy-session-3",
                attributionId: "legacy-probe-3",
                category: null,
                description: "非该对象",
                source: "fresh",
                confidence: 0.4,
              },
            ],
          },
        })),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(finalStep)),
    );
    const wrapper = await mountPage();

    const info = wrapper.get("[data-testid='run-info-panel']");
    expect(info.text()).toContain("2 / 1");
    expect(info.text()).toContain("＝ 归因 2 · 复用缓存 0 · 本次新增 2");
    expect(info.text()).not.toContain("3 / 1");
  });

  it("shares the range step query with the info panel when step=range is selected", async () => {
    let rangeRequests = 0;
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({ status: "completed" }),
            ["done", "done", "done", "done", "done", "done", "done"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/range`, () => {
        rangeRequests += 1;
        return HttpResponse.json(rangeStep);
      }),
      http.get(`${evolutionBase}/runs/:runId/steps/attribution`, () =>
        HttpResponse.json(attributionStep)),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(finalStep)),
    );
    await mountPage("evo-full-1", "?step=range");

    expect(rangeRequests).toBe(1);
  });

  it("submits a manual retry, disables the button, and refetches the run", async () => {
    const nextRetryAt = new Date(2026, 9, 27, 12, 5, 0).toISOString();
    let detailCalls = 0;
    let retryCalls = 0;
    let releaseRetry: () => void = () => undefined;
    const retryGate = new Promise<void>((resolve) => {
      releaseRetry = resolve;
    });
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () => {
        detailCalls += 1;
        return HttpResponse.json(
          detail(
            run({
              status: "blocked",
              error: {
                stage: "eval",
                message: "评测执行失败：sandbox timeout",
                at: "2026-10-27T12:00:00+08:00",
              },
            }),
            ["done", "done", "done", "done", "done", "active", "pending"],
            { blockedStage: "eval", retryAttempts: 1, nextRetryAt },
          ),
        );
      }),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(iterationStep)),
      http.post(`${evolutionBase}/runs/:runId/retry`, async () => {
        retryCalls += 1;
        await retryGate;
        return HttpResponse.json(
          { jobId: "job-retry-1", reused: false },
          { status: 202 },
        );
      }),
    );
    const wrapper = await mountPage();
    const button = wrapper.get("[data-testid='run-retry']");

    await button.trigger("click");
    await flushPromises();

    expect(retryCalls).toBe(1);
    expect(button.attributes("disabled")).toBeDefined();

    releaseRetry();
    await vi.waitFor(() => expect(detailCalls).toBe(2));
    await flushPromises();

    expect(button.attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-testid='retry-accepted']").text()).toContain(
      "重试任务已受理",
    );
  });

  it("restores the retry button when an accepted retry never advances the run", async () => {
    const nextRetryAt = new Date(2026, 9, 27, 12, 5, 0).toISOString();
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "blocked",
              error: {
                stage: "eval",
                message: "评测执行失败：sandbox timeout",
                at: "2026-10-27T12:00:00+08:00",
              },
            }),
            ["done", "done", "done", "done", "done", "active", "pending"],
            { blockedStage: "eval", retryAttempts: 1, nextRetryAt },
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(iterationStep)),
      http.post(`${evolutionBase}/runs/:runId/retry`, () =>
        HttpResponse.json(
          { jobId: "job-retry-1", reused: false },
          { status: 202 },
        )),
    );
    const wrapper = await mountPage();
    const button = wrapper.get("[data-testid='run-retry']");

    vi.useFakeTimers();
    try {
      await button.trigger("click");
      await vi.waitFor(() => expect(button.text()).toBe("已提交重试"));
      expect(button.attributes("disabled")).toBeDefined();

      await vi.advanceTimersByTimeAsync(10_000);
      await flushPromises();

      expect(button.text()).toBe("重试");
      expect(button.attributes("disabled")).toBeUndefined();
      expect(wrapper.find("[data-testid='retry-accepted']").exists()).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it("clears the accepted retry when a new blocked snapshot shows different facts", async () => {
    const errorAt = "2026-10-27T12:00:00+08:00";
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "blocked",
              error: {
                stage: "eval",
                message: "评测执行失败：sandbox timeout",
                at: errorAt,
              },
            }),
            ["done", "done", "done", "done", "done", "active", "pending"],
            { blockedStage: "eval", retryAttempts: 1, nextRetryAt: null },
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(iterationStep)),
      http.post(`${evolutionBase}/runs/:runId/retry`, () =>
        HttpResponse.json(
          { jobId: "job-retry-1", reused: false },
          { status: 202 },
        )),
    );
    const wrapper = await mountPage();
    const button = wrapper.get("[data-testid='run-retry']");

    await button.trigger("click");
    await vi.waitFor(() => expect(button.text()).toBe("已提交重试"));

    const refreshed = detail(
      run({
        status: "blocked",
        error: {
          stage: "eval",
          message: "评测执行失败：sandbox timeout",
          at: "2026-10-27T12:02:00+08:00",
        },
      }),
      ["done", "done", "done", "done", "done", "active", "pending"],
      { blockedStage: "eval", retryAttempts: 2, nextRetryAt: null },
    );
    activeQueryClient?.setQueryData(queryKeys.evolutionRun(workspaceId, "evo-full-1"), refreshed);

    await vi.waitFor(() => expect(button.text()).toBe("重试"));
    expect(button.attributes("disabled")).toBeUndefined();
    expect(wrapper.find("[data-testid='retry-accepted']").exists()).toBe(false);
  });

  it("shows an inline error when the run is no longer retryable", async () => {
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "blocked",
              error: {
                stage: "push",
                message: "push failed",
                at: "2026-10-27T12:00:00+08:00",
              },
            }),
            ["done", "done", "done", "done", "done", "active", "pending"],
            { blockedStage: "push" },
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(iterationStep)),
      http.post(`${evolutionBase}/runs/:runId/retry`, () =>
        HttpResponse.json(
          {
            error: {
              code: "RUN_NOT_RETRYABLE",
              message: "run is not blocked",
            },
          },
          { status: 409 },
        )),
    );
    const wrapper = await mountPage();

    await wrapper.get("[data-testid='run-retry']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-testid='retry-error']").text()).toContain(
      "当前不可重试",
    );
    expect(
      wrapper.get("[data-testid='run-retry']").attributes("disabled"),
    ).toBeUndefined();
  });

  it("reports a missing run when the retry endpoint returns 404", async () => {
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({ status: "blocked" }),
            ["done", "done", "done", "done", "done", "active", "pending"],
            { blockedStage: "eval" },
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(iterationStep)),
      http.post(`${evolutionBase}/runs/:runId/retry`, () =>
        HttpResponse.json(
          {
            error: {
              code: "RUN_NOT_FOUND",
              message: "evolution run not found",
            },
          },
          { status: 404 },
        )),
    );
    const wrapper = await mountPage();

    await wrapper.get("[data-testid='run-retry']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-testid='retry-error']").text()).toContain(
      "运行不存在或已被删除",
    );
  });

  it("maps retry validation failures to actionable copy", async () => {
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({ status: "blocked" }),
            ["done", "done", "done", "done", "done", "active", "pending"],
            { blockedStage: "eval" },
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(iterationStep)),
      http.post(`${evolutionBase}/runs/:runId/retry`, () =>
        HttpResponse.json(
          {
            error: {
              code: "VALIDATION_INVALID",
              message: "request validation failed",
              details: {
                errors: [
                  {
                    loc: ["body", "reason"],
                    msg: "Value error, invalid retry reason",
                    type: "value_error",
                  },
                ],
              },
            },
          },
          { status: 422 },
        ),
      ),
    );
    const wrapper = await mountPage();

    await wrapper.get("[data-testid='run-retry']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-testid='retry-error']").text()).toContain(
      "请求体字段格式不正确，请按字段要求修改后再试",
    );
    expect(wrapper.get("[data-testid='retry-error']").text()).not.toContain(
      "invalid retry reason",
    );
  });

  it("explains an interrupted run without offering a retry", async () => {
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({
              status: "interrupted",
              error: {
                stage: "eval",
                message: "进程重启，任务被中断",
                at: "2026-10-27T12:00:00+08:00",
              },
            }),
            ["pending", "pending", "pending", "pending", "pending", "pending", "pending"],
          ),
        )),
    );
    const wrapper = await mountPage();

    expect(wrapper.get("[data-testid='interrupted-banner']").text()).toContain(
      "任务被中断，系统将自动恢复；可查看最后事件",
    );
    expect(wrapper.find("[data-testid='run-retry']").exists()).toBe(false);
  });

  it("appends live SSE events to the execution log", async () => {
    const existingEvent = {
      seq: 1,
      eventType: "run_created",
      level: "info",
      stage: "prepare",
      stepIndex: null,
      clusterId: null,
      roundId: null,
      jobId: null,
      message: "已有事件",
      createdAt: "2026-10-27T12:00:00+08:00",
      payload: null,
      error: null,
    };
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({ status: "running" }),
            ["done", "done", "done", "done", "done", "active", "pending"],
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(iterationStep)),
      http.get(`${evolutionBase}/runs/:runId/events`, () =>
        HttpResponse.json({
          items: [existingEvent],
          nextSeq: 1,
          hasMore: false,
        })),
    );
    const wrapper = await mountPage("evo-full-1", "?tab=logs");

    expect(wrapper.get("[data-testid='run-log-panel']").text()).toContain(
      "已有事件",
    );

    TestEventSource.latest().emit("run.event", {
      ...existingEvent,
      seq: 2,
      eventType: "eval_completed",
      level: "warn",
      stage: "eval",
      message: "SSE 新事件",
    });
    await flushPromises();

    expect(wrapper.get("[data-testid='run-log-panel']").text()).toContain(
      "SSE 新事件",
    );
    expect(wrapper.get("[data-testid='run-log-panel']").text()).toContain(
      "2 条",
    );
  });

  it("seeds the SSE cursor from the run snapshot high-water mark", async () => {
    let lastEventId = -1;
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          detail(
            run({ status: "running" }),
            ["done", "done", "done", "done", "done", "active", "pending"],
            { lastEventSeq: 105 },
          ),
        )),
      http.get(`${evolutionBase}/runs/:runId/steps/:step`, () =>
        HttpResponse.json(iterationStep)),
      http.post("/api/events/ticket", async ({ request }) => {
        const body = (await request.json()) as { lastEventId?: number };
        lastEventId = body.lastEventId ?? -1;
        return HttpResponse.json({
          ticket: "snapshot-ticket",
          expiresIn: 60,
          topics: ["run:evo-full-1"],
        });
      }),
    );
    await mountPage();

    await vi.waitFor(() => expect(lastEventId).toBe(105));
  });

  it("shows a retryable error when the run list request fails", async () => {
    let attempts = 0;
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              { error: { code: "INTERNAL", message: "failed" } },
              { status: 500 },
            )
          : HttpResponse.json(detail());
      }),
      http.get(`${evolutionBase}/runs/evo-full-1/steps/range`, () =>
        HttpResponse.json(rangeStep)),
    );
    const wrapper = await mountPage();

    expect(wrapper.get(".error-state").attributes("role")).toBe("alert");
    expect(wrapper.get(".error-state").text()).toContain(
      "运行详情读取失败，请重试",
    );

    await wrapper.get(".error-state button").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-step-key='range']").attributes("aria-current")).toBe(
      "step",
    );
  });

  it("reports a missing run without offering a retry", async () => {
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json(
          {
            error: {
              code: "RUN_NOT_FOUND",
              message: "evolution run not found",
            },
          },
          { status: 404 },
        )),
    );
    const wrapper = await mountPage("evo-missing");

    expect(wrapper.text()).toContain("运行不存在或已被删除");
    expect(wrapper.find(".error-state button").exists()).toBe(false);
  });

  it("opens durable execution history from the error banner", async () => {
    server.use(
      http.get(`${evolutionBase}/runs/:runId`, () =>
        HttpResponse.json({
          ...detail(
            run({
              status: "failed",
              error: {
                stage: "prepare",
                message: "仓库 clone 失败",
                at: "2026-10-27T12:00:00+08:00",
              },
            }),
            ["pending", "pending", "pending", "pending", "pending", "pending", "pending"],
          ),
          lastEventSeq: 2,
        })),
      http.get(`${evolutionBase}/runs/:runId/events`, () =>
        HttpResponse.json({
          items: [
            {
              seq: 1,
              eventType: "run_created",
              level: "info",
              stage: "prepare",
              stepIndex: null,
              clusterId: null,
              roundId: null,
              jobId: null,
              message: "运行已创建",
              createdAt: "2026-10-27T12:00:00+08:00",
              payload: null,
              error: null,
            },
            {
              seq: 2,
              eventType: "run_failed",
              level: "error",
              stage: "prepare",
              stepIndex: null,
              clusterId: null,
              roundId: null,
              jobId: "job-1",
              message: "准备失败",
              createdAt: "2026-10-27T12:00:01+08:00",
              payload: null,
              error: {
                type: "GitError",
                message: "clone failed",
                detail: "token=<redacted>",
              },
            },
          ],
          nextSeq: 2,
          hasMore: false,
        })),
    );
    const wrapper = await mountPage();

    await wrapper.get("[data-testid='open-error-log']").trigger("click");
    await flushPromises();

    expect(wrapper.vm.$route.query.tab).toBe("logs");
    expect(wrapper.get("[data-testid='run-log-panel']").text()).toContain(
      "准备失败",
    );
    expect(wrapper.text()).toContain("clone failed");
  });
});
