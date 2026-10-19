import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { metaLine } from "./fixtures";
import { createMemorySnapshotSource } from "./memory-source";

function familySource() {
  return createMemorySnapshotSource({
    "root-cont.jsonl": [metaLine({ threadId: "r", timestamp: "2026-10-18T01:00:00.000Z" })],
    "root.jsonl": [metaLine({ threadId: "r" })],
    "a.jsonl": [
      metaLine({
        threadId: "a",
        sessionId: "r",
        parentThreadId: "r",
        depth: 1,
        agentPath: "/root/a",
        nickname: "A",
      }),
    ],
    "b.jsonl": [
      metaLine({
        threadId: "b",
        sessionId: "r",
        parentThreadId: "r",
        depth: 1,
        agentPath: "/root/b",
        nickname: "B",
      }),
    ],
    "c.jsonl": [
      metaLine({
        threadId: "c",
        sessionId: "r",
        parentThreadId: "a",
        depth: 2,
        agentPath: "/root/a/c",
        nickname: "C",
      }),
    ],
    "guardian.jsonl": [
      metaLine({ threadId: "g", sessionId: "r", parentThreadId: "r", other: "guardian" }),
    ],
    "unrelated.jsonl": [metaLine({ threadId: "u" })],
  });
}

describe("buildFamilyIndex", () => {
  it("builds the tree, groups segments, and excludes guardian threads", async () => {
    const source = familySource();
    const index = await buildFamilyIndex({ roots: ["r"], source });
    const family = index.families[0];

    expect(family).toBeDefined();
    expect(family?.agents.map((agent) => agent.threadId)).toEqual(["r", "a", "b", "c"]);
    expect(family?.agents.find((agent) => agent.threadId === "g")).toBeUndefined();
    expect(family?.agents.find((agent) => agent.threadId === "r")?.segments).toHaveLength(2);
    expect(family?.agents.find((agent) => agent.threadId === "r")?.segments.filter((segment) => segment.primary)).toHaveLength(1);
    expect(family?.stats.rolloutCount).toBe(4);
    expect(family?.stats.segmentCount).toBe(5);
    expect(family?.stats.maxDepth).toBe(2);
    expect(source.calls.readRecords).toBe(0);
  });

  it("does not let a reused session id overwrite another agent", async () => {
    const index = await buildFamilyIndex({ roots: ["r"], source: familySource() });
    const family = index.families[0];
    const a = family?.agents.find((agent) => agent.threadId === "a");
    const b = family?.agents.find((agent) => agent.threadId === "b");

    expect(a?.sessionId).toBe("r");
    expect(b?.sessionId).toBe("r");
    expect(a?.threadId).not.toBe(b?.threadId);
  });

  it("reports a missing root without throwing", async () => {
    const index = await buildFamilyIndex({ roots: ["missing"], source: familySource() });

    expect(index.families).toHaveLength(0);
    expect(index.diagnostics).toContainEqual(
      expect.objectContaining({ code: "missing-root", threadId: "missing" }),
    );
  });
});
