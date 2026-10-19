import { describe, expect, it } from "vitest";
import type { SessionFamily } from "@harness/contracts";

describe("session family contracts", () => {
  it("accepts the four-family snapshot shape", () => {
    const family = {
      rootThreadId: "root",
      rootSessionId: "session",
      rootAgentPath: "/",
      label: null,
      agents: [],
      findings: [],
      skills: [],
      stats: {
        rolloutCount: 0,
        segmentCount: 0,
        recordCount: null,
        continuationRecordCount: null,
        byteCount: 0,
        maxDepth: 0,
        agentCount: 0,
        findingCount: 0,
      },
      diagnostics: [],
    } satisfies SessionFamily;

    expect(family.stats.recordCount).toBeNull();
  });
});
