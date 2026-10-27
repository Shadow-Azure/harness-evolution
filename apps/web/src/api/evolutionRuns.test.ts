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

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const response: EvolutionRunList = {
  running: [],
  history: [],
};

describe("evolution run API", () => {
  it("reads the backend-grouped run list from the exact endpoint", async () => {
    let method = "";
    let path = "";
    server.use(
      http.get("/api/evolution/runs", ({ request }) => {
        method = request.method;
        path = new URL(request.url).pathname;
        return HttpResponse.json(response);
      }),
    );

    await expect(listEvolutionRuns()).resolves.toEqual(response);
    expect(method).toBe("GET");
    expect(path).toBe("/api/evolution/runs");
  });

  it("reads one run step from the key-specific endpoint", async () => {
    let path = "";
    server.use(
      http.get("/api/evolution/runs/:runId/steps/:step", ({ request }) => {
        path = new URL(request.url).pathname;
        return HttpResponse.json({
          key: "iteration",
          index: 4,
          title: "迭代优化",
          status: "active",
          clickable: true,
          payload: { rounds: [] },
        });
      }),
    );

    const response = await getEvolutionRunStep("run with spaces", "iteration");

    expect(response.key).toBe("iteration");
    expect(path).toBe("/api/evolution/runs/run%20with%20spaces/steps/iteration");
  });

  it("reads execution events with the documented cursor and level filter", async () => {
    let query = "";
    server.use(
      http.get("/api/evolution/runs/:runId/events", ({ request }) => {
        query = new URL(request.url).search;
        return HttpResponse.json({
          items: [],
          nextSeq: 12,
          hasMore: false,
        });
      }),
    );

    const response = await listEvolutionRunEvents("run events", {
      afterSeq: 12,
      limit: 50,
      level: "warn",
    });

    expect(response.nextSeq).toBe(12);
    expect(query).toBe("?afterSeq=12&limit=50&level=warn");
  });
});
