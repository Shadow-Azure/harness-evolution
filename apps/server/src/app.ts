import Fastify from "fastify";
import type { HealthResponse } from "@harness/contracts";

/**
 * HTTP composition root.
 *
 * Feature routes will be registered here as vertical slices, for example:
 * - sessions
 * - ingest
 * - analyses
 * @returns 已注册当前路由的 Fastify 实例；调用方负责 listen 与错误处置。
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
