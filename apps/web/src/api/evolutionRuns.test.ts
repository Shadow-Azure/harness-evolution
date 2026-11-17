// @vitest-environment jsdom

import type { EvolutionRunList } from "@harness/contracts";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  getEvolutionRunStep,
  listEvolutionRunEvents,
  listEvolutionRuns,
  previewAttribution,
  previewPotential,
  previewSessions,
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
    expect(calls[0].body).toMatchObject({ page: 1, pageSize: 4 });
    expect(calls[1].body).toMatchObject({
      policy: { preset: "default" },
      pageSize: 5,
    });
    expect(calls[2].body).toMatchObject({ cacheEnabled: true });
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
});
