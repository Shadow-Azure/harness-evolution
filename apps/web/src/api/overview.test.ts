// @vitest-environment jsdom

import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  getOverviewSources,
  getOverviewSummary,
  getOverviewTrend,
  listOverviewBadCases,
} from "./overview";
import { server } from "../test/server";

const workspaceId = "ws-test";
const overviewBase = `/api/workspaces/${workspaceId}/overview`;
const casesBase = `/api/workspaces/${workspaceId}/bad-cases`;

let requestedUrl = "";

function capture(url: string) {
  requestedUrl = url;
}

const summaryPayload = {
  window: { from: "2026-08-19", to: "2026-11-16" },
  totals: {
    badCases: 3,
    self: 2,
    discovery: 1,
    sessions: 2,
    sources: 2,
    quota: 60,
    used: 3,
  },
  objects: ["deep-research", "workflow"],
};

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  requestedUrl = "";
});
afterAll(() => server.close());

describe("overview api", () => {
  it("sends the quick range and the object union as one comma list", async () => {
    server.use(
      http.get(`${overviewBase}/summary`, ({ request }) => {
        capture(request.url);
        return HttpResponse.json(summaryPayload);
      }),
    );

    const summary = await getOverviewSummary(workspaceId, {
      range: 30,
      objects: [" deep-research ", "workflow", "deep-research", ""],
    });

    const url = new URL(requestedUrl);
    expect(url.pathname).toBe(`${overviewBase}/summary`);
    expect(url.searchParams.get("range")).toBe("30");
    expect(url.searchParams.get("objects")).toBe("deep-research,workflow");
    expect(summary).toEqual(summaryPayload);
  });

  it("prefers an explicit window over the quick range", async () => {
    server.use(
      http.get(`${overviewBase}/summary`, ({ request }) => {
        capture(request.url);
        return HttpResponse.json(summaryPayload);
      }),
    );

    await getOverviewSummary(workspaceId, {
      range: 90,
      from: "2026-10-01",
      to: "2026-10-31",
    });

    const url = new URL(requestedUrl);
    expect(url.searchParams.get("from")).toBe("2026-10-01");
    expect(url.searchParams.get("to")).toBe("2026-10-31");
    expect(url.searchParams.has("range")).toBe(false);
  });

  it("omits an empty object filter instead of sending a blank value", async () => {
    server.use(
      http.get(`${overviewBase}/sources`, ({ request }) => {
        capture(request.url);
        return HttpResponse.json({
          items: [
            { object: "deep-research", total: 2, self: 1, discovery: 1, sessions: 1 },
          ],
        });
      }),
    );

    const sources = await getOverviewSources(workspaceId, {
      range: 7,
      objects: [],
    });

    const url = new URL(requestedUrl);
    expect(url.searchParams.has("objects")).toBe(false);
    expect(url.searchParams.get("range")).toBe("7");
    expect(sources.items).toHaveLength(1);
  });

  it("sends the requested trend grain and keeps the effective grain from the server", async () => {
    const payload = {
      window: { from: "2026-08-19", to: "2026-11-16" },
      grain: "week",
      buckets: [
        { bucket: "2026-11-09", label: "11-09", self: 1, discovery: 0, total: 1 },
      ],
    };
    server.use(
      http.get(`${overviewBase}/trend`, ({ request }) => {
        capture(request.url);
        return HttpResponse.json(payload);
      }),
    );

    const trend = await getOverviewTrend(workspaceId, {
      range: 90,
      grain: "day",
      objects: ["workflow"],
    });

    const url = new URL(requestedUrl);
    expect(url.searchParams.get("grain")).toBe("day");
    expect(url.searchParams.get("objects")).toBe("workflow");
    expect(trend.grain).toBe("week");
    expect(trend.buckets[0]?.total).toBe(1);
  });

  it("pages the case list at eight rows and omits the all type", async () => {
    server.use(
      http.get(casesBase, ({ request }) => {
        capture(request.url);
        return HttpResponse.json({
          items: [],
          total: 0,
          page: 1,
          pageSize: 8,
        });
      }),
    );

    await listOverviewBadCases(workspaceId, {
      range: 90,
      badCaseType: "all",
    });

    const url = new URL(requestedUrl);
    expect(url.pathname).toBe(casesBase);
    expect(url.searchParams.get("range")).toBe("90");
    expect(url.searchParams.get("page")).toBe("1");
    expect(url.searchParams.get("pageSize")).toBe("8");
    expect(url.searchParams.has("badCaseType")).toBe(false);
  });

  it("sends an explicit page and a concrete bad-case type", async () => {
    server.use(
      http.get(casesBase, ({ request }) => {
        capture(request.url);
        return HttpResponse.json({
          items: [],
          total: 0,
          page: 2,
          pageSize: 8,
        });
      }),
    );

    await listOverviewBadCases(workspaceId, {
      from: "2026-10-01",
      to: "2026-10-31",
      objects: ["deep-research"],
      badCaseType: "discovery",
      page: 2,
      pageSize: 8,
    });

    const url = new URL(requestedUrl);
    expect(url.searchParams.get("from")).toBe("2026-10-01");
    expect(url.searchParams.get("badCaseType")).toBe("discovery");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("objects")).toBe("deep-research");
  });
});
