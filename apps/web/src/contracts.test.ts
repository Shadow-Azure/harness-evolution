import { describe, expect, expectTypeOf, it } from "vitest";

import type {
  DatabaseDialect,
  ErrorResponse,
  HealthResponse,
  ServicePhase,
} from "@harness/contracts";

describe("generated API contracts", () => {
  it("accepts healthy and unavailable health payloads", () => {
    const healthy = {
      ok: true,
      service: "harness-evolution",
      phase: "scaffold",
      version: "0.1.0",
      db: { dialect: "sqlite", ok: true, latencyMs: 0.2 },
    } satisfies HealthResponse;
    const unavailable = {
      ok: false,
      service: "harness-evolution",
      phase: "live",
      version: "0.1.0",
      db: {
        dialect: "mysql",
        ok: false,
        latencyMs: 1.4,
        error: "OperationalError: database is unavailable",
      },
    } satisfies HealthResponse;

    expect(healthy.db.dialect).toBe("sqlite");
    expect(unavailable.db.error).toContain("OperationalError");
    expectTypeOf<ServicePhase>().toEqualTypeOf<"scaffold" | "demo" | "live">();
    expectTypeOf<DatabaseDialect>().toEqualTypeOf<"sqlite" | "mysql">();
  });

  it("uses the generated error envelope", () => {
    const response = {
      error: {
        code: "AUTH_REQUIRED",
        message: "authentication is required",
        details: {},
      },
    } satisfies ErrorResponse;

    expect(response.error.code).toBe("AUTH_REQUIRED");
  });
});
