// @vitest-environment jsdom

import type { EvolutionRunList } from "@harness/contracts";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  cancelAttributionJob,
  getEvolutionRunStep,
  listAttributionJobs,
  listEvolutionRunEvents,
  listEvolutionRuns,
  pauseEvolutionRun,
  resumeEvolutionRun,
  previewAttribution,
  previewPotential,
  previewSessions,
  retryAttributionJob,
  startAttributionJob,
} from "./evolutionRuns";
import { server } from "../test/server";

const workspaceId = "ws-test";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const response: EvolutionRunList = {
  running: [],
  history: [],
};

describe("evolution run API", () => {
  it("posts workspace-scoped pause and resume with encoded run IDs and accepted status codes", async () => {
    const calls: string[] = [];
    const control = { runId: "run with spaces", controlState: "pause_requested", canPause: false, canResume: false };
    server.use(http.post("/api/workspaces/:wid/evolution/runs/:runId/:action", ({ request, params }) => {
      calls.push(new URL(request.url).pathname);
      return HttpResponse.json({ ...control, controlState: params.action === "resume" ? "running" : "pause_requested" }, { status: params.action === "resume" ? 200 : 202 });
    }));
    await expect(pauseEvolutionRun(workspaceId, control.runId)).resolves.toMatchObject({ controlState: "pause_requested" });
    await expect(resumeEvolutionRun(workspaceId, control.runId)).resolves.toMatchObject({ controlState: "running" });
    expect(calls).toEqual([
      "/api/workspaces/ws-test/evolution/runs/run%20with%20spaces/pause",
      "/api/workspaces/ws-test/evolution/runs/run%20with%20spaces/resume",
    ]);
  });

  it("reads the workspace run list from the exact endpoint", async () => {
    let method = "";
    let path = "";
    server.use(
      http.get(`/api/workspaces/${workspaceId}/evolution/runs`, ({ request }) => {
        method = request.method;
        path = new URL(request.url).pathname;
        return HttpResponse.json(response);
      }),
    );

    await expect(listEvolutionRuns(workspaceId)).resolves.toEqual(response);
    expect(method).toBe("GET");
    expect(path).toBe(`/api/workspaces/${workspaceId}/evolution/runs`);
  });

  it("reads one run step from the key-specific workspace endpoint", async () => {
    let path = "";
    server.use(
      http.get(
        "/api/workspaces/:wid/evolution/runs/:runId/steps/:step",
        ({ request }) => {
          path = new URL(request.url).pathname;
          return HttpResponse.json({
            key: "iteration",
            index: 4,
            title: "迭代优化",
            status: "active",
            clickable: true,
            payload: { rounds: [] },
          });
        },
      ),
    );

    const step = await getEvolutionRunStep(
      workspaceId,
      "run with spaces",
      "iteration",
    );

    expect(step.key).toBe("iteration");
    expect(path).toBe(
      `/api/workspaces/${workspaceId}/evolution/runs/run%20with%20spaces/steps/iteration`,
    );
  });

  it("posts each wizard preview to its workspace endpoint", async () => {
    const calls: { path: string; body: unknown }[] = [];
    server.use(
      http.post(
        "/api/workspaces/:wid/evolution/preview/sessions",
        async ({ request }) => {
          calls.push({
            path: new URL(request.url).pathname,
            body: await request.json(),
          });
          return HttpResponse.json({
            summary: {
              reported: 1,
              associated: 1,
              skipped: 0,
              versionUnresolved: 0,
              pending: 0,
            },
            items: [],
            total: 0,
            page: 1,
            pageSize: 4,
          });
        },
      ),
      http.post(
        "/api/workspaces/:wid/evolution/preview/potential",
        async ({ request }) => {
          calls.push({
            path: new URL(request.url).pathname,
            body: await request.json(),
          });
          return HttpResponse.json({
            summary: {
              badCases: 0,
              potential: 0,
              byReason: {
                selfReport: 0,
                afterObject: 0,
                both: 0,
                orderUnknown: 0,
                policyExcluded: 0,
              },
            },
            items: [],
            total: 0,
            page: 1,
            pageSize: 5,
          });
        },
      ),
      http.post(
        "/api/workspaces/:wid/evolution/preview/attribution",
        async ({ request }) => {
          calls.push({
            path: new URL(request.url).pathname,
            body: await request.json(),
          });
          return HttpResponse.json({
            summary: { potential: 0, reused: 0, fresh: 0, nonTargetKnown: 0 },
          });
        },
      ),
    );

    const condition = {
      targetType: "skill" as const,
      targetName: "deep-research",
      targetVersion: "v2.0.0",
      from: "2026-10-01",
      to: "2026-10-31",
    };
    await previewSessions(workspaceId, {
      ...condition,
      page: 1,
      pageSize: 4,
    });
    await previewPotential(workspaceId, {
      ...condition,
      policy: { preset: "default" },
      page: 1,
      pageSize: 5,
    });
    await previewAttribution(workspaceId, {
      ...condition,
      policy: { preset: "default" },
      cacheEnabled: true,
    });

    expect(calls.map((call) => call.path)).toEqual([
      `/api/workspaces/${workspaceId}/evolution/preview/sessions`,
      `/api/workspaces/${workspaceId}/evolution/preview/potential`,
      `/api/workspaces/${workspaceId}/evolution/preview/attribution`,
    ]);
    expect(calls[0]!.body).toMatchObject({ page: 1, pageSize: 4 });
    expect(calls[1]!.body).toMatchObject({
      policy: { preset: "default" },
      pageSize: 5,
    });
    expect(calls[2]!.body).toMatchObject({ cacheEnabled: true });
  });

  it("sends the Session default page and explicit potential pagination", async () => {
    const queries: string[] = [];
    server.use(
      http.get(
        "/api/workspaces/:wid/evolution/runs/:runId/steps/:step",
        ({ request }) => {
          queries.push(new URL(request.url).search);
          return HttpResponse.json({ key: "sessions" });
        },
      ),
    );

    await getEvolutionRunStep(workspaceId, "run-1", "sessions");
    await getEvolutionRunStep(workspaceId, "run-1", "potential", 2, 5);

    expect(queries).toEqual(["?page=1&pageSize=4", "?page=2&pageSize=5"]);
  });

  it("reads execution events with the documented cursor and level filter", async () => {
    let query = "";
    server.use(
      http.get(
        "/api/workspaces/:wid/evolution/runs/:runId/events",
        ({ request }) => {
          query = new URL(request.url).search;
          return HttpResponse.json({
            items: [],
            nextSeq: 12,
            hasMore: false,
          });
        },
      ),
    );

    const page = await listEvolutionRunEvents(workspaceId, "run events", {
      afterSeq: 12,
      limit: 50,
      level: "warn",
    });

    expect(page.nextSeq).toBe(12);
    expect(query).toBe("?afterSeq=12&limit=50&level=warn");
  });

  it("uses workspace-scoped attribution job control endpoints", async () => {
    const calls: string[] = [];
    const job = {
      jobId: "job-1",
      runId: "run jobs",
      source: "manual",
      status: "queued",
      progress: 0,
      attempt: 0,
      maxAttempts: 3,
      cancelRequested: false,
      observation: {
        total: 0,
        completed: 0,
        created: 0,
        reused: 0,
        failed: 0,
        nonTarget: 0,
        averageLatencyMs: 0,
        p95LatencyMs: 0,
        tokenCount: 0,
        warningCount: 0,
        evidenceCoverageRate: 0,
        executor: "rule-v1",
        skillRevision: null,
        contextHash: null,
      },
      error: null,
      createdAt: "2026-11-18T10:00:00+08:00",
      startedAt: null,
      finishedAt: null,
    };
    server.use(
      http.get("/api/workspaces/:wid/evolution/runs/:runId/attribution-jobs", ({ request }) => {
        calls.push(`${request.method} ${new URL(request.url).pathname}`);
        return HttpResponse.json({ items: [job] });
      }),
      http.post(
        "/api/workspaces/:wid/evolution/runs/:runId/attribution-jobs",
        ({ request }) => {
          calls.push(`${request.method} ${new URL(request.url).pathname}`);
          return HttpResponse.json(job, { status: 202 });
        },
      ),
      http.post(
        "/api/workspaces/:wid/evolution/runs/:runId/attribution-jobs/:jobId/retry",
        ({ request }) => {
          calls.push(`${request.method} ${new URL(request.url).pathname}`);
          return HttpResponse.json(job, { status: 202 });
        },
      ),
      http.post(
        "/api/workspaces/:wid/evolution/runs/:runId/attribution-jobs/:jobId/cancel",
        ({ request }) => {
          calls.push(`${request.method} ${new URL(request.url).pathname}`);
          return HttpResponse.json({ ...job, status: "cancelled" });
        },
      ),
    );

    await listAttributionJobs(workspaceId, "run jobs");
    await startAttributionJob(workspaceId, "run jobs");
    await retryAttributionJob(workspaceId, "run jobs", "job 1");
    await cancelAttributionJob(workspaceId, "run jobs", "job 1");

    expect(calls).toEqual([
      "GET /api/workspaces/ws-test/evolution/runs/run%20jobs/attribution-jobs",
      "POST /api/workspaces/ws-test/evolution/runs/run%20jobs/attribution-jobs",
      "POST /api/workspaces/ws-test/evolution/runs/run%20jobs/attribution-jobs/job%201/retry",
      "POST /api/workspaces/ws-test/evolution/runs/run%20jobs/attribution-jobs/job%201/cancel",
    ]);
  });
});
