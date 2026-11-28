// @vitest-environment jsdom

import type { EvolutionRunCard, EvolutionStepAttribution } from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { server } from "../../../test/server";
import StepAttribution from "./StepAttribution.vue";

const workspaceId = "ws-test";
const runId = "run-observed";
const endpoint = `/api/workspaces/${workspaceId}/evolution/runs/${runId}/attribution-jobs`;

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const step = {
  key: "attribution",
  index: 3,
  title: "对象归因",
  status: "active",
  clickable: true,
  payload: {
    summary: { potential: 2, reused: 1, fresh: 1, nonTarget: 0 },
    rows: [],
  },
} as EvolutionStepAttribution;

const run = {
  runId,
  controlState: "running",
  canPause: false,
  canResume: false,
  degraded: false,
  title: "归因观测",
  mode: "full",
  policy: { preset: "default" },
  cacheEnabled: true,
  target: { type: "skill", name: "Explore", version: "v1", subDir: "skills/Explore", matchByName: false },
  window: { from: null, to: null },
  models: [],
  createdBy: null,
  createdAt: "2026-11-18T10:00:00+08:00",
  status: "blocked",
  error: null,
  stats: {
    sessions: 1,
    versionUnresolvedSessions: 0,
    badCases: 2,
    potential: 2,
    attributed: 1,
    reused: 1,
    clusters: 0,
    byCategory: { flow: 0, context: 0, model: 1, prompt: 0, error: 0 },
  },
  progress: {
    unit: 3,
    total: 7,
    percent: 43,
    stageLabel: "对象归因中",
    doneRounds: 0,
    accepted: 0,
  },
  final: null,
} satisfies EvolutionRunCard;

function failedJob() {
  return {
    jobId: "job-failed",
    runId,
    source: "prepare",
    status: "failed",
    progress: 0.5,
    attempt: 1,
    maxAttempts: 3,
    cancelRequested: false,
    observation: {
      total: 2,
      completed: 2,
      created: 1,
      reused: 0,
      failed: 1,
      nonTarget: 0,
      averageLatencyMs: 320,
      p95LatencyMs: 610,
      tokenCount: 128,
      warningCount: 1,
      evidenceCoverageRate: 0.5,
      executor: "agent-skill-stub-v1",
      skillRevision: "default@r2",
      contextHash: null,
    },
    error: "rate limited",
    createdAt: "2026-11-18T10:00:00+08:00",
    startedAt: "2026-11-18T10:00:01+08:00",
    finishedAt: "2026-11-18T10:00:03+08:00",
  };
}

describe("attribution job observability", () => {
  it("renders all category labels and keeps verdicts with no category distinct", async () => {
    server.use(http.get(endpoint, () => HttpResponse.json({ items: [] })));
    const cases = [
      ["attributed", "model", "模型问题"],
      ["attributed", "prompt", "提示词问题"],
      ["attributed", "error", "错误"],
      ["attributed", "flow", "流程"],
      ["attributed", "context", "上下文"],
      ["non_target", null, "非该对象问题"],
      ["inconclusive", null, "证据不足"],
      [null, null, "非该对象问题"],
    ] as const;
    const rows = cases.map(([conclusion, category], index) => ({
      conclusion,
      category,
      attributionId: `report-${index}`,
      badCaseId: `case-${index}`,
      sessionId: "session-1",
      description: "合成报告",
      confidence: null,
      source: "fresh" as const,
    }));
    const wrapper = mount(StepAttribution, {
      props: { wid: workspaceId, run, step: { ...step, payload: { ...step.payload, rows } } },
      global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] },
    });
    await flushPromises();
    expect(wrapper.findAll("tbody .type-chip").map((chip) => chip.text()))
      .toEqual(cases.map(([, , label]) => label));
    wrapper.unmount();
  });

  it("renders sanitized metrics and retries only the failed durable job", async () => {
    let retries = 0;
    server.use(
      http.get(endpoint, () => HttpResponse.json({ items: [failedJob()] })),
      http.post(`${endpoint}/job-failed/retry`, () => {
        retries += 1;
        return HttpResponse.json(
          { ...failedJob(), status: "queued", error: null },
          { status: 202 },
        );
      }),
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const wrapper = mount(StepAttribution, {
      props: { wid: workspaceId, canWrite: true, step, run },
      global: { plugins: [[VueQueryPlugin, { queryClient }]] },
    });
    await flushPromises();

    expect(wrapper.get("[data-testid='attribution-job-runtime']").text()).toContain("P95 610ms");
    expect(wrapper.text()).toContain("证据覆盖 50%");
    for (const controlState of ["pause_requested", "paused"] as const) {
      await wrapper.setProps({ run: { ...run, controlState } });
      expect(wrapper.find("button.primary").exists()).toBe(false);
      expect(wrapper.get("[data-testid='attribution-job-runtime']").text()).toContain("失败");
    }
    await wrapper.setProps({ run });
    await wrapper.get("button.primary").trigger("click");
    await flushPromises();
    expect(retries).toBe(1);
    queryClient.clear();
    wrapper.unmount();
  });
});
