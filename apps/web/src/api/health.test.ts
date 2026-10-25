import { describe, expect, it, vi } from "vitest";
import { healthFixtures } from "@harness/contracts";

import { fetchHealth } from "./health";

describe("health API", () => {
  it("returns the shared contract payload", async () => {
    const payload = healthFixtures.healthy;
    const response = Response.json(payload);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    await expect(fetchHealth()).resolves.toEqual(payload);
  });

  it("accepts the canonical degraded health contract", async () => {
    const payload = healthFixtures.unavailable;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json(payload, { status: 503 })),
    );

    await expect(fetchHealth()).resolves.toEqual(payload);
  });

  it("turns transport failures into ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    await expect(fetchHealth()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });

  it("rejects an error envelope returned with a health HTTP status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json(
          {
            error: {
              code: "HEALTH_UNAVAILABLE",
              message: "database unavailable",
            },
          },
          { status: 503 },
        ),
      ),
    );

    await expect(fetchHealth()).rejects.toMatchObject({
      code: "HEALTH_UNAVAILABLE",
      message: "database unavailable",
      status: 503,
    });
  });

  it("rejects a malformed success payload before the shell reads it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ ok: true, phase: "scaffold" })),
    );

    await expect(fetchHealth()).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
      status: 200,
    });
  });
});
