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

  it("turns transport failures into ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    await expect(fetchHealth()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});
