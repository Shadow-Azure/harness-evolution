import { describe, expect, it } from "vitest";

import { ApiError } from "./http";
import { createAppQueryClient } from "./queryClient";

describe("createAppQueryClient", () => {
  it("installs the shared query defaults", () => {
    const client = createAppQueryClient();
    const defaults = client.getDefaultOptions().queries;

    expect(defaults?.gcTime).toBe(5 * 60 * 1000);
    expect(defaults?.refetchOnWindowFocus).toBe(false);
    expect(defaults?.staleTime).toBe(30 * 1000);
    const retry = defaults?.retry;
    expect(typeof retry).toBe("function");
    if (typeof retry !== "function") {
      throw new Error("query retry must be a function");
    }
    expect(retry(0, new ApiError(401, "AUTH_REQUIRED", "missing"))).toBe(false);
    expect(retry(0, new ApiError(503, "INTERNAL", "unavailable"))).toBe(true);
    expect(retry(2, new ApiError(503, "INTERNAL", "unavailable"))).toBe(false);
  });
});
