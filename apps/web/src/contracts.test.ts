import { describe, expect, expectTypeOf, it } from "vitest";

import type {
  DatabaseDialect,
  ErrorResponse,
  HealthResponse,
  ServicePhase,
} from "@harness/contracts";
import { healthFixtures } from "@harness/contracts";

describe("generated API contracts", () => {
  it("accepts healthy and unavailable health payloads", () => {
    const healthy = healthFixtures.healthy satisfies HealthResponse;
    const unavailable = healthFixtures.unavailable satisfies HealthResponse;

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
