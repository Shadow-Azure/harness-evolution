import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { healthFixtures } from "@harness/contracts";

/** MSW node server; this module is imported only from tests. */
export const server = setupServer(
  http.get("/api/health", () => HttpResponse.json(healthFixtures.healthy)),
  http.post("/api/auth/refresh", () =>
    HttpResponse.json(
      { error: { code: "AUTH_EXPIRED", message: "no refresh cookie" } },
      { status: 401 },
    ),
  ),
);
