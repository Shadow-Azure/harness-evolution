import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { eventLine, metaLine, responseLine } from "./fixtures";
import { loadRollout } from "./load";
import { createMemorySnapshotSource } from "./memory-source";

function source() {
  return createMemorySnapshotSource({
    "root.jsonl": [
      metaLine({ threadId: "r" }),
      responseLine(1, { type: "message", role: "user", content: [{ type: "input_text", text: "root" }] }),
      eventLine(2, { type: "task_complete", turn_id: "t1" }),
    ],
    "root-cont.jsonl": [
      metaLine({ threadId: "r", timestamp: "2026-10-18T01:00:00.000Z" }),
      responseLine(3, { type: "message", role: "user", content: [{ type: "input_text", text: "continued" }] }),
    ],
    "a.jsonl": [
      metaLine({ threadId: "a", parentThreadId: "r", depth: 1, agentPath: "/root/a" }),
      responseLine(1, { type: "message", role: "user", content: [{ type: "input_text", text: "child" }] }),
      eventLine(2, { type: "task_complete", turn_id: "t2" }),
    ],
  });
}

describe("loadRollout", () => {
  it("reads only the requested agent and infers status from turns", async () => {
    const memory = source();
    const index = await buildFamilyIndex({ roots: ["r"], source: memory });
    const family = index.families[0];
    if (!family) throw new Error("family missing");

    const loaded = await loadRollout({ threadId: "a", family, source: memory });

    expect(memory.calls.recordsRolloutIds).toEqual(["a.jsonl"]);
    expect(loaded.records).toHaveLength(3);
    expect(loaded.timeline.map((item) => item.kind)).toEqual(["user-message", "turn"]);
    expect(loaded.status).toBe("completed");
    expect(loaded.stats.recordCount).toBe(3);
    expect(loaded.skills).toEqual([]);
  });

  it("loads continuation segments only when requested", async () => {
    const memory = source();
    const index = await buildFamilyIndex({ roots: ["r"], source: memory });
    const family = index.families[0];
    if (!family) throw new Error("family missing");

    await loadRollout({ threadId: "r", family, source: memory });
    expect(memory.calls.recordsRolloutIds).toEqual(["root.jsonl"]);

    memory.calls.recordsRolloutIds.length = 0;
    await loadRollout({ threadId: "r", family, source: memory, includeContinuation: true });
    expect(memory.calls.recordsRolloutIds.sort()).toEqual(["root-cont.jsonl", "root.jsonl"]);
  });
});
