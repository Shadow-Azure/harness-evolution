import type { EvolutionRunDetail } from "@harness/contracts";
import { describe, expect, it } from "vitest";

import { runDetailRefetchInterval } from "./useEvolutionRunDetail";

function snapshot(status: EvolutionRunDetail["status"]): EvolutionRunDetail {
  return { status } as EvolutionRunDetail;
}

describe("runDetailRefetchInterval", () => {
  it("polls blocked runs faster so the sweeper retry is visible", () => {
    expect(runDetailRefetchInterval(snapshot("blocked"))).toBe(5_000);
  });

  it("keeps a slow polling fallback behind the live stream", () => {
    expect(runDetailRefetchInterval(snapshot("preparing"))).toBe(15_000);
    expect(runDetailRefetchInterval(snapshot("running"))).toBe(15_000);
  });

  it("stops polling for terminal and unknown snapshots", () => {
    expect(runDetailRefetchInterval(snapshot("completed"))).toBe(false);
    expect(runDetailRefetchInterval(snapshot("failed"))).toBe(false);
    expect(runDetailRefetchInterval(snapshot("interrupted"))).toBe(false);
    expect(runDetailRefetchInterval(undefined)).toBe(false);
  });
});
