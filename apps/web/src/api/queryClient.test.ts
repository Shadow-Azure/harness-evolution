import { describe, expect, it } from "vitest";

import { createAppQueryClient } from "./queryClient";

describe("createAppQueryClient", () => {
  it("installs the shared query defaults", () => {
    const client = createAppQueryClient();
    const defaults = client.getDefaultOptions().queries;

    expect(defaults?.gcTime).toBe(5 * 60 * 1000);
    expect(defaults?.retry).toBe(false);
    expect(defaults?.staleTime).toBe(30 * 1000);
  });
});
