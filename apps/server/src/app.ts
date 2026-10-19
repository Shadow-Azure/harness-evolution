import Fastify from "fastify";
import type { HealthResponse } from "@harness/contracts";

/**
 * HTTP composition root.
 *
 * Feature routes will be registered here as vertical slices, for example:
 * - sessions
 * - ingest
 * - analyses
 */
export function buildApp() {
  const app = Fastify({
    logger: true
  });

  app.get("/api/health", async (): Promise<HealthResponse> => {
    return {
      ok: true,
      service: "harness-evolution",
      phase: "scaffold"
    };
  });

  return app;
}
