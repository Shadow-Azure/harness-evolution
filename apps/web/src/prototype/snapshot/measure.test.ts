import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { eventLine, metaLine, responseLine } from "./fixtures";
import { countAgentStats, measureFamily } from "./measure";
import { createMemorySnapshotSource } from "./memory-source";
import { toRecord } from "./meta";

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

  it("counts tool failures and completed failed items", () => {
    const agent = {
      threadId: "root",
      sessionId: "root",
      parentThreadId: null,
      depth: 0,
      agentPath: "/",
      nickname: null,
      role: null,
      kind: "root" as const,
      segments: [
        {
          rolloutId: "root.jsonl",
          threadId: "root",
          startedAt: "2026-10-18T00:00:00.000Z",
          byteCount: 10,
          recordCount: null,
          primary: true,
        },
      ],
      children: [],
      stats: {
        segmentCount: 1,
        recordCount: null,
        continuationRecordCount: null,
        byteCount: 0,
        turnCount: null,
        toolCallCount: null,
        failureCount: null,
        findingCount: 2,
      },
    };
    const records = [
      responseLine(1, { type: "function_call", call_id: "call-1", name: "exec_command" }),
      responseLine(2, {
        type: "function_call_output",
        call_id: "call-1",
        output: "Process exited with code 1",
      }),
      responseLine(3, { type: "custom_tool_call", call_id: "call-2", name: "tool" }),
      responseLine(4, {
        type: "custom_tool_call_output",
        call_id: "call-2",
        output: "Failed to find expected lines",
      }),
      eventLine(5, {
        type: "item_completed",
        item: { type: "CommandExecution", status: "failed" },
      }),
      eventLine(6, {
        type: "item_completed",
        item: { type: "McpToolCall", status: "failed" },
      }),
      eventLine(7, {
        type: "item_completed",
        item: { type: "CommandExecution", status: "completed" },
      }),
    ]
      .map((line, index) => toRecord("root.jsonl", line, index + 1))
      .filter((record): record is NonNullable<typeof record> => record !== null);

    const stats = countAgentStats(agent, records);

    expect(stats.toolCallCount).toBe(2);
    expect(stats.failureCount).toBe(4);
    expect(stats.findingCount).toBe(2);
  });
});
