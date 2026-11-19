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
  title: "归因观测",
  mode: "full",
  target: { type: "skill", name: "Explore", version: "v1" },
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
} as EvolutionRunCard;

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
      props: { workspaceId, canWrite: true, step, run },
      global: { plugins: [[VueQueryPlugin, { queryClient }]] },
    });
    await flushPromises();

    expect(wrapper.get("[data-testid='attribution-job-runtime']").text()).toContain("P95 610ms");
    expect(wrapper.text()).toContain("证据覆盖 50%");
    await wrapper.get("button.primary").trigger("click");
    await flushPromises();
    expect(retries).toBe(1);
    queryClient.clear();
    wrapper.unmount();
  });
});
