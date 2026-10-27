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

const emptyHits = {
  sessions: 0,
  badCases: 0,
  analyzed: 0,
  unanalyzed: 0,
  probes: 0,
  usedProbes: 0,
  byAttributeType: { model: 0, prompt: 0, error: 0, nonIssue: 0 },
};

function run(overrides: Partial<EvolutionRunCard> = {}): EvolutionRunCard {
  return {
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
        model: 12,
        prompt: 8,
        error: 8,
        nonIssue: 18,
      },
    },
    progress: {
      unit: 0,
      total: 6,
      percent: 0,
      stageLabel: "第 1/6 步 · 筛选输入中…",
      doneRounds: 0,
      accepted: 0,
    },
    final: null,
    ...overrides,
  };
}

const inputStep = {
  key: "input",
  index: 0,
  title: "筛选输入",
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
      models: ["glm-5.3"],
    },
    hits: emptyHits,
    rows: [],
  },
};

const iterationStep = {
  key: "iteration",
  index: 4,
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
        type: "error",
        probeCount: 1,
        confidence: 0.82,
        severity: 7.4,
        probes: [
          {
            probeId: "pr-1",
            sessionId: "session-1",
            sessionTitle: "研究",
            model: "glm-5.3",
            probeType: "skill",
            probeObject: "deep-research",
            objectVersion: "v2.0.0",
            attributeType: "error",
            description: "读取越界",
            sourceBadCaseIds: ["bc-1"],
          },
        ],
        status: "evaluating",
        candidate: {
          ref: "evo/run/candidate/r1",
          commit: "abc123",
          message: "candidate",
        },
        patch: {
          file: "SKILL.md",
          lines: [
            "@@ -1 +1 @@",
            "- 读取索引",
            "+ 读取索引前校验快照",
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
    ["input", "筛选输入"],
    ["clusters", "问题聚类"],
    ["attribution", "LLM 归因置信度"],
    ["severity", "严重程度排序"],
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
) {
  return {
    ...card,
    blockedStage: card.status === "blocked" ? "eval" : null,
    retryAttempts: card.status === "blocked" ? 1 : 0,
    nextRetryAt: null,
    evalStatus: card.status === "blocked" ? "failed" : "pending",
    workspace: {
      repoUrl: "https://example.invalid/skills.git",
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
    lastEventSeq: 0,
    steps: detailSteps(statuses),
  };
}

async function mountPage(runId = "evo-full-1", query = "") {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/evolution", component: { template: "<div />" } },
      { path: "/evolution/runs/:runId", component: RunDetail },
      { path: "/evolution/cluster/:runId", component: { template: "<div />" } },
      {
        path: "/sessions/:sessionId/errors",
        component: { template: "<div />" },
      },
    ],
  });
  await router.push(`/evolution/runs/${runId}${query}`);
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
  it("shows an unreached explanation when a failed run stops before step 1", async () => {
    const requested: string[] = [];
    server.use(
      http.get("/api/evolution/runs/:runId", () =>
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
                total: 6,
                percent: 0,
                stageLabel: "准备运行",
                doneRounds: 0,
                accepted: 0,
              },
            }),
            ["pending", "pending", "pending", "pending", "pending", "pending"],
          ),
        )),
      http.get("/api/evolution/runs/:runId/steps/:step", ({ params }) => {
        requested.push(String(params.step));
        return HttpResponse.json(inputStep);
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
      http.get("/api/evolution/runs/:runId", () =>
        HttpResponse.json(detail())),
      http.get("/api/evolution/runs/evo-full-1/steps/input", () =>
        HttpResponse.json(inputStep)),
    );
    const wrapper = await mountPage();

    const button = wrapper.get("[data-testid='copy-branch']");
    expect(button.element.tagName).toBe("BUTTON");
    await button.trigger("click");
    await flushPromises();

    expect(writes).toEqual(["evo/evo-full-1"]);
    expect(button.text()).toContain("已复制");
  });

  it("renders the preparing input step and keeps later steps disabled", async () => {
    server.use(
      http.get("/api/evolution/runs/:runId", () =>
        HttpResponse.json(detail())),
      http.get("/api/evolution/runs/evo-full-1/steps/input", () =>
        HttpResponse.json(inputStep)),
    );
    const wrapper = await mountPage();

    expect(wrapper.get("h1").text()).toBe("deep-research v2.0.0 自进化");
    expect(wrapper.findAll("[data-step-key]")).toHaveLength(6);
    expect(wrapper.get("[data-step-key='input']").attributes("aria-current")).toBe(
      "step",
    );
    expect(wrapper.get("[data-step-key='clusters']").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-step-key='clusters']").attributes("title")).toBe(
      "该步骤尚未到达",
    );
    expect(wrapper.text()).toContain("准备中");
    expect(wrapper.text()).toContain("evo/evo-full-1");
    expect(wrapper.text()).toContain("当前条件下没有已分析的问题 probe");
    expect(wrapper.find("[data-testid='evolution-cluster-preview']").exists()).toBe(
      false,
    );
  });

  it("loads only the active iteration and shows candidate/eval state", async () => {
    const requested: string[] = [];
    server.use(
      http.get("/api/evolution/runs/:runId", () =>
        HttpResponse.json(
          detail(
            run({
              status: "running",
              progress: {
                unit: 4,
                total: 6,
                percent: 67,
                stageLabel: "第 5/6 步 · 迭代优化 · 第 1/2 轮",
                doneRounds: 0,
                accepted: 0,
              },
            }),
            ["done", "done", "done", "done", "active", "pending"],
          ),
        )),
      http.get("/api/evolution/runs/:runId/steps/:step", ({ params }) => {
        requested.push(String(params.step));
        return HttpResponse.json(iterationStep);
      }),
    );
    const wrapper = await mountPage();

    expect(requested).toEqual(["iteration"]);
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
      http.get("/api/evolution/runs/:runId", () =>
        HttpResponse.json(
          detail(
            run({
              status: "running",
              progress: {
                unit: 4,
                total: 6,
                percent: 67,
                stageLabel: "第 5/6 步 · 迭代优化 · 第 1/2 轮",
                doneRounds: 0,
                accepted: 0,
              },
            }),
            ["done", "done", "done", "done", "active", "pending"],
          ),
        )),
      http.get("/api/evolution/runs/:runId/steps/:step", ({ params }) => {
        const key = String(params.step);
        requested.push(key);
        if (key === "iteration") return HttpResponse.json(iterationStep);
        return HttpResponse.json({
          key: "clusters",
          index: 1,
          title: "问题聚类",
          status: "done",
          clickable: true,
          payload: {
            clusters: [
              {
                probeClusterId: "C1",
                title: "检索索引读取失败",
                description: "读取越界",
                type: "error",
                probeCount: 1,
                confidence: 0.82,
                severity: 7.4,
                probes: [],
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
      "/evolution/runs/evo-full-1?step=clusters",
    );
    expect(requested).toEqual(["iteration", "clusters"]);
    expect(wrapper.get("[data-step-key='clusters']").attributes("aria-current")).toBe(
      "step",
    );
    expect(wrapper.text()).toContain("M=1 类");
  });

  it("removes a missing cluster deep-link while retaining the notice", async () => {
    server.use(
      http.get("/api/evolution/runs/:runId", () =>
        HttpResponse.json(
          detail(
            run({ status: "completed" }),
            ["done", "done", "done", "done", "done", "done"],
          ),
        )),
      http.get("/api/evolution/runs/:runId/steps/:step", () =>
        HttpResponse.json({
          key: "clusters",
          index: 1,
          title: "问题聚类",
          status: "done",
          clickable: true,
          payload: {
            clusters: [
              {
                probeClusterId: "C1",
                title: "检索索引读取失败",
                description: "读取越界",
                type: "error",
                probeCount: 1,
                confidence: 0.82,
                severity: 7.4,
                probes: [],
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
      "/evolution/runs/evo-full-1?step=clusters",
    );
    expect(wrapper.text()).toContain("目标簇已不存在");
  });

  it("loads a completed run's final verdict by default", async () => {
    const requested: string[] = [];
    server.use(
      http.get("/api/evolution/runs/:runId", () =>
        HttpResponse.json(
          detail(
            run({
              status: "completed",
              progress: {
                unit: 6,
                total: 6,
                percent: 100,
                stageLabel: "第 6/6 步 · 测试集终评中…",
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
            ["done", "done", "done", "done", "done", "done"],
          ),
        )),
      http.get("/api/evolution/runs/:runId/steps/:step", ({ params }) => {
        requested.push(String(params.step));
        return HttpResponse.json({
          key: "final",
          index: 5,
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
                type: "error",
                reportCount: 1,
              },
            ],
          },
        });
      }),
    );
    const wrapper = await mountPage();

    expect(requested).toEqual(["final"]);
    expect(wrapper.text()).toContain("✓ 自进化有效");
    expect(wrapper.text()).toContain("任务完成率");
    expect(wrapper.text()).toContain("cd34ab");
    expect(wrapper.get("[data-step-key='final']").attributes("aria-current")).toBe(
      "step",
    );
  });

  it("keeps blocked context visible above the selected step", async () => {
    server.use(
      http.get("/api/evolution/runs/:runId", () =>
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
                probes: 46,
                usedProbes: 28,
                clusters: 1,
                byAttributeType: {
                  model: 12,
                  prompt: 8,
                  error: 8,
                  nonIssue: 18,
                },
              },
              progress: {
                unit: 4,
                total: 5,
                percent: 80,
                stageLabel: "第 5/6 步 · 迭代优化 · 第 1/1 轮",
                doneRounds: 0,
                accepted: 0,
              },
            }),
            ["done", "done", "done", "done", "active", "pending"],
          ),
        )),
      http.get("/api/evolution/runs/:runId/steps/:step", () =>
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

    expect(wrapper.get("[data-testid='blocked-banner']").text()).toContain(
      "评测执行失败：sandbox timeout",
    );
    expect(wrapper.get("[data-testid='blocked-banner']").text()).toContain(
      "eval",
    );
    expect(wrapper.get("[data-testid='blocked-banner']").text()).toContain(
      "自动重试 1 次",
    );
    expect(wrapper.text()).toContain("评测失败");
  });

  it("shows a retryable error when the run list request fails", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/evolution/runs/:runId", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              { error: { code: "INTERNAL", message: "failed" } },
              { status: 500 },
            )
          : HttpResponse.json(detail());
      }),
      http.get("/api/evolution/runs/evo-full-1/steps/input", () =>
        HttpResponse.json(inputStep)),
    );
    const wrapper = await mountPage();

    expect(wrapper.get(".error-state").attributes("role")).toBe("alert");
    expect(wrapper.get(".error-state").text()).toContain(
      "运行详情读取失败，请重试",
    );

    await wrapper.get(".error-state button").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-step-key='input']").attributes("aria-current")).toBe(
      "step",
    );
  });

  it("reports a missing run without offering a retry", async () => {
    server.use(
      http.get("/api/evolution/runs/:runId", () =>
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
});
