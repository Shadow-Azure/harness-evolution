import { describe, expect, it } from "vitest";

import { resolveVersionLabel } from "./versionLabel";

const DIGEST = "digest:580c97cf8ca79018df6692fd4db3cc8193b44cc91e51d1f9127b5818f1bf107";

describe("resolveVersionLabel", () => {
  it("prefers the run ref and short commit over the stored digest", () => {
    expect(resolveVersionLabel(DIGEST, "v2.2.0", "5c41d7a")).toEqual({
      ref: "v2.2.0",
      commit: "5c41d7a",
      digest: null,
      missing: false,
      full: "v2.2.0 5c41d7a",
      copy: "5c41d7a",
    });
  });

  it("keeps a digest fallback when the run has no readable evidence", () => {
    expect(resolveVersionLabel(DIGEST, null, null)).toEqual({
      ref: null,
      commit: null,
      digest: DIGEST,
      missing: false,
      full: DIGEST,
      copy: DIGEST,
    });
  });

  it("shows a commit-only label when the ref is a bare commit", () => {
    expect(resolveVersionLabel("a3f9c21d4e5f60718293a4b5c6d7e8f901234567", null, null)).toEqual({
      ref: null,
      commit: "a3f9c21d4e5f60718293a4b5c6d7e8f901234567",
      digest: null,
      missing: false,
      full: "a3f9c21d4e5f60718293a4b5c6d7e8f901234567",
      copy: "a3f9c21d4e5f60718293a4b5c6d7e8f901234567",
    });
  });

  it("treats a plain legacy version as the ref", () => {
    expect(resolveVersionLabel("2026.11.1", null, null)).toEqual({
      ref: "2026.11.1",
      commit: null,
      digest: null,
      missing: false,
      full: "2026.11.1",
      copy: "2026.11.1",
    });
  });

  it("reports an unpinned version without a copy value", () => {
    expect(resolveVersionLabel(null, null, null)).toEqual({
      ref: null,
      commit: null,
      digest: null,
      missing: true,
      full: "版本未固定",
      copy: null,
    });
  });

  it("drops a digest accidentally supplied through the ref slot", () => {
    const display = resolveVersionLabel(DIGEST, DIGEST, null);
    expect(display.ref).toBeNull();
    expect(display.digest).toBe(DIGEST);
  });
});
