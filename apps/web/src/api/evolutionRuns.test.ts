// @vitest-environment jsdom

import type { EvolutionRunList } from "@harness/contracts";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { listEvolutionRuns } from "./evolutionRuns";
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
});
