// @vitest-environment jsdom

import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import {
  getOverviewSources,
  getOverviewSummary,
  getOverviewTargetDetail,
  getOverviewTargetsTrend,
  getOverviewTrend,
  listAllOverviewTargets,
  listOverviewBadCases,
  listOverviewTargetCases,
} from "./overview";
import { server } from "../test/server";

const workspaceId = "ws-test";
const overviewBase = `/api/workspaces/${workspaceId}/overview`;
const casesBase = `/api/workspaces/${workspaceId}/bad-cases`;

let requestedUrl = "";
const requestedUrls: string[] = [];

function capture(url: string) {
  requestedUrl = url;
  requestedUrls.push(url);
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
  requestedUrls.length = 0;
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


describe("evolution-target overview api", () => {
  it("sends the target selection, states, and grain to the target trend", async () => {
    server.use(
      http.get(`${overviewBase}/targets/trend`, ({ request }) => {
        capture(request.url);
        return HttpResponse.json({
          window: { from: "2026-08-19", to: "2026-11-16" },
          grain: "week",
          buckets: [],
          meta: { bucketPolicy: "attribution then report time" },
        });
      }),
    );

    await getOverviewTargetsTrend(workspaceId, {
      range: 30,
      grain: "day",
      targets: [" target-1 ", "target-2", "target-1"],
      states: ["attributed", "unanalyzed", "attributed"],
    });

    const url = new URL(requestedUrl);
    expect(url.pathname).toBe(`${overviewBase}/targets/trend`);
    expect(url.searchParams.get("range")).toBe("30");
    expect(url.searchParams.get("grain")).toBe("day");
    expect(url.searchParams.get("targets")).toBe("target-1,target-2");
    expect(url.searchParams.get("states")).toBe("attributed,unanalyzed");
  });

  it("follows target pages until total and keeps the server order", async () => {
    const all = Array.from({ length: 55 }, (_, index) => ({
      targetId: `target-${index + 1}`,
      objectType: "skill",
      objectName: `object-${index + 1}`,
      versions: ["main"],
      sessions: 0,
      potential: 0,
      attributed: 0,
      nonTarget: 0,
      unanalyzed: 0,
      evolvable: 0,
    }));
    server.use(
      http.get(`${overviewBase}/targets`, ({ request }) => {
        capture(request.url);
        const url = new URL(request.url);
        const page = Number(url.searchParams.get("page") ?? "1");
        const pageSize = Number(url.searchParams.get("pageSize") ?? "5");
        return HttpResponse.json({
          summary: {
            targets: all.length,
            sessions: 0,
            potential: 0,
            attributed: 0,
            nonTarget: 0,
            unanalyzed: 0,
          },
          items: all.slice((page - 1) * pageSize, page * pageSize),
          total: all.length,
          page,
          pageSize,
        });
      }),
    );

    const response = await listAllOverviewTargets(workspaceId, { range: 90 });

    expect(response.items).toHaveLength(55);
    expect(response.items[0]?.targetId).toBe("target-1");
    expect(requestedUrls).toHaveLength(2);
    expect(new URL(requestedUrls[1] as string).searchParams.get("page")).toBe("2");
    expect(new URL(requestedUrls[0] as string).searchParams.get("pageSize")).toBe(
      "50",
    );
  });

  it("pages potential cases with target, source, and state filters", async () => {
    server.use(
      http.get(`${overviewBase}/targets/cases`, ({ request }) => {
        capture(request.url);
        return HttpResponse.json({ items: [], total: 0, page: 2, pageSize: 8 });
      }),
    );

    await listOverviewTargetCases(workspaceId, {
      from: "2026-10-01",
      to: "2026-10-31",
      targets: ["target-1"],
      objects: [" Explore ", "Explore"],
      states: ["nonTarget"],
      page: 2,
    });

    const url = new URL(requestedUrl);
    expect(url.pathname).toBe(`${overviewBase}/targets/cases`);
    expect(url.searchParams.get("from")).toBe("2026-10-01");
    expect(url.searchParams.get("to")).toBe("2026-10-31");
    expect(url.searchParams.get("targets")).toBe("target-1");
    expect(url.searchParams.get("objects")).toBe("Explore");
    expect(url.searchParams.get("states")).toBe("nonTarget");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("pageSize")).toBe("8");
  });

  it("sends explicit versions and the version limit to one target detail", async () => {
    server.use(
      http.get(`${overviewBase}/targets/:targetId/detail`, ({ request }) => {
        capture(request.url);
        return HttpResponse.json({
          target: {
            targetId: "target-1",
            objectType: "skill",
            objectName: "synthetic-review",
            defaultRef: "main",
            versions: ["main"],
          },
          stats: { sessions: 0, potential: 0, distinctCases: 0, versions: 0 },
          byVersion: [],
          bySource: [],
        });
      }),
    );

    await getOverviewTargetDetail(workspaceId, "target/1", {
      range: 7,
      versions: [" main ", "main"],
      versionLimit: 10,
    });

    const url = new URL(requestedUrl);
    expect(url.pathname).toBe(`${overviewBase}/targets/target%2F1/detail`);
    expect(url.searchParams.get("range")).toBe("7");
    expect(url.searchParams.get("versions")).toBe("main");
    expect(url.searchParams.get("versionLimit")).toBe("10");
  });
});
