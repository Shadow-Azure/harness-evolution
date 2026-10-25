import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { healthFixtures } from "@harness/contracts";

/** MSW node server; this module is imported only from tests. */
export const server = setupServer(
  http.get("/api/health", () => HttpResponse.json(healthFixtures.healthy)),
  http.get("/api/sessions", () => HttpResponse.json({ items: [] })),
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
      errors: []
    }),
  ),
  http.post("/api/auth/refresh", () =>
    HttpResponse.json(
      { error: { code: "AUTH_EXPIRED", message: "no refresh cookie" } },
      { status: 401 },
    ),
  ),
);
