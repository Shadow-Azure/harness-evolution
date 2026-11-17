// @vitest-environment jsdom

import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { getAttribution, getAttributionPage } from "./badCases";
import { server } from "../test/server";

const workspaceId = "ws test";
const badCaseId = "case/1";
const attributionId = "AT 1";
const base = `/api/workspaces/${encodeURIComponent(workspaceId)}/bad-cases/${encodeURIComponent(badCaseId)}`;

let requestedUrl = "";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  requestedUrl = "";
});
afterAll(() => server.close());

describe("attribution reads", () => {
  it("requests one encoded workspace page with the default two rows", async () => {
    server.use(
      http.get(`${base}/attributions`, ({ request }) => {
        requestedUrl = request.url;
        return HttpResponse.json({
          items: [],
          total: 0,
          page: 2,
          pageSize: 2,
        });
      }),
    );

    await getAttributionPage(workspaceId, badCaseId, 2);

    const url = new URL(requestedUrl);
    expect(url.pathname).toBe(base + "/attributions");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("pageSize")).toBe("2");
  });

  it("allows the detail navigator to request a wider page", async () => {
    server.use(
      http.get(`${base}/attributions`, ({ request }) => {
        requestedUrl = request.url;
        return HttpResponse.json({
          items: [],
          total: 0,
          page: 1,
          pageSize: 50,
        });
      }),
    );

    await getAttributionPage(workspaceId, badCaseId, 1, 50);

    const url = new URL(requestedUrl);
    expect(url.searchParams.get("pageSize")).toBe("50");
  });

  it("encodes both the case and attribution identifiers in the detail path", async () => {
    server.use(
      http.get(`${base}/attributions/:attributionId`, ({ request }) => {
        requestedUrl = request.url;
        return HttpResponse.json({
          attributionId: "AT 1",
          badCaseId: "case/1",
          objectType: "agent",
          objectName: "Explore",
          objectVersion: null,
          conclusion: "attributed",
          category: null,
          confidence: 0.5,
          runId: null,
          isCached: false,
          reusedCount: 0,
          createdAt: "2026-10-20T09:03:30+08:00",
          updatedAt: "2026-10-20T09:03:30+08:00",
          reason: "reason",
          reasoning: "reasoning",
          policyVersion: "v2",
          attributionEngine: "engine",
          triggerCompare: {
            objectTriggerAt: null,
            caseTriggerAt: null,
            order: "unknown",
            versionState: "unknown",
          },
          warnings: [],
        });
      }),
    );

    const detail = await getAttribution(workspaceId, badCaseId, attributionId);

    const url = new URL(requestedUrl);
    expect(url.pathname).toBe(
      base + `/attributions/${encodeURIComponent(attributionId)}`,
    );
    expect(detail.attributionId).toBe("AT 1");
  });
});
