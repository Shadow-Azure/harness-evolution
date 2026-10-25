import { describe, expect, it } from "vitest";

import { safeRedirect } from "./safeRedirect";

describe("safeRedirect", () => {
  it("keeps app-relative deep links", () => {
    expect(safeRedirect("/sessions/s-1?q=error#top")).toBe("/sessions/s-1?q=error#top");
  });

  it.each([undefined, "", "https://evil.example", "//evil.example", "/\\evil.example"])(
    "falls back for unsafe target %s",
    (candidate) => {
      expect(safeRedirect(candidate)).toBe("/sessions");
    },
  );
});
