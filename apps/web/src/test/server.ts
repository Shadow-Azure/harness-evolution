import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { healthFixtures } from "@harness/contracts";

/** MSW node server; this module is imported only from tests. */
export const server = setupServer(
  http.get("/api/health", () => HttpResponse.json(healthFixtures.healthy)),
  http.get("/api/sessions", () => HttpResponse.json({ items: [] })),
  http.get("/api/evolution/runs", () =>
    HttpResponse.json({ running: [], history: [] }),
  ),
  http.post("/api/events/ticket", () =>
    HttpResponse.json({
      ticket: "test-ticket",
      expiresIn: 60,
      topics: [],
    }),
  ),
  http.get("/api/acquisition/status", () =>
    HttpResponse.json({
      activeJobId: null,
      status: "idle",
      payloadTable: "trajectory_payloads",
      pending: 0,
      processed: 0,
      imported: 0,
      skipped: 0,
      lastRunAt: null,
      nextRunAt: null,
      errors: [],
      badCaseSync: {
        total: 0,
        synced: 0,
        unsynced: 0,
        syncing: 0,
        failed: 0,
        status: "idle",
        lastRunAt: null,
        lastError: null
      },
      badCaseCatalogSync: {
        synced: 0,
        unsynced: 0,
        lastBadCaseId: 0,
        status: "idle",
        lastRunAt: null,
        lastError: null
      },
      badCaseAnalysis: {
        total: 0,
        analyzed: 0,
        pending: 0,
        issue: 0,
        nonIssue: 0
      }
    }),
  ),
  http.post("/api/auth/refresh", () =>
    HttpResponse.json(
      { error: { code: "AUTH_EXPIRED", message: "no refresh cookie" } },
      { status: 401 },
    ),
  ),
  http.get("/api/sessions/:sessionId/bad-cases", () =>
    HttpResponse.json({ items: [] }),
  ),
  http.get(
    "/api/workspaces/:workspaceId/evolution/targets/:targetId/attribution-skill",
    () =>
      HttpResponse.json({
        id: "revision-platform-1",
        skillId: "skill-platform",
        workspaceId: null,
        skillKey: "platform-default",
        displayName: "平台默认归因",
        description: "固定规则归因",
        builtIn: true,
        enabled: true,
        revision: 1,
        content: { engine: "rule-v1" },
        contentHash: "a".repeat(64),
        executorType: "builtin_rule",
        outputSchemaVersion: "probe-report/v2",
        status: "published",
        source: "platform",
      }),
  ),
);
