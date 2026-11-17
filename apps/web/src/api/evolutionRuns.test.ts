// @vitest-environment jsdom

import type { EvolutionRunList } from "@harness/contracts";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  getEvolutionRunStep,
  listEvolutionRunEvents,
  listEvolutionRuns,
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
            index: 5,
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

  it("sends the Session default page and explicit potential pagination", async () => {
    const queries: string[] = [];
    server.use(
      http.get(
        "/api/workspaces/:wid/evolution/runs/:runId/steps/:step",
        ({ request }) => {
          queries.push(new URL(request.url).search);
          return HttpResponse.json({
            key: "sessions",
            index: 1,
            title: "Session 关联",
            status: "done",
            clickable: true,
            payload: {
              summary: {
                reported: 0,
                associated: 0,
                skipped: 0,
                versionUnresolved: 0,
                pending: 0,
              },
              rows: [],
              total: 0,
              page: 1,
              pageSize: 4,
            },
          });
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
});
