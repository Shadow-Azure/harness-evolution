import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { eventLine, metaLine, responseLine } from "./fixtures";
import { measureFamily } from "./measure";
import { createMemorySnapshotSource } from "./memory-source";

describe("measureFamily", () => {
  it("counts primary and continuation records separately", async () => {
    const source = createMemorySnapshotSource({
      "root.jsonl": [
        metaLine({ threadId: "r" }),
        responseLine(1, { type: "message", role: "user", content: [] }),
        eventLine(2, { type: "task_complete", turn_id: "t1" }),
      ],
      "root-cont.jsonl": [
        metaLine({ threadId: "r", timestamp: "2026-10-18T01:00:00.000Z" }),
      ],
      "a.jsonl": [
        metaLine({ threadId: "a", parentThreadId: "r", depth: 1, agentPath: "/root/a" }),
        responseLine(1, { type: "message", role: "user", content: [] }),
      ],
    });
    const index = await buildFamilyIndex({ roots: ["r"], source });
    const family = index.families[0];
    if (!family) throw new Error("family missing");

    const measured = await measureFamily({ family, source });

    expect(measured.stats.recordCount).toBe(5);
    expect(measured.stats.continuationRecordCount).toBe(1);
    expect(measured.stats.rolloutCount).toBe(2);
    expect(measured.stats.segmentCount).toBe(3);
    expect(measured.stats.maxDepth).toBe(1);
    expect(measured.agents.find((agent) => agent.threadId === "a")?.stats.recordCount).toBe(2);
    expect(source.calls.recordsRolloutIds.sort()).toEqual([
      "a.jsonl",
      "root-cont.jsonl",
      "root.jsonl",
    ]);
  });
});
