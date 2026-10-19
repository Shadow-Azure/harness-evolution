import { describe, expect, it } from "vitest";
import type { AgentNode } from "@harness/contracts";
import { eventLine, responseLine, tokenLine } from "./fixtures";
import { toRecord } from "./meta";
import { toTimelineItems } from "./timeline";

const agent: AgentNode = {
  threadId: "r",
  sessionId: "r",
  parentThreadId: null,
  depth: 0,
  agentPath: "/",
  nickname: null,
  role: null,
  kind: "root",
  segments: [],
  children: [],
  stats: {
    segmentCount: 1,
    recordCount: null,
    continuationRecordCount: null,
    byteCount: 0,
    turnCount: null,
    toolCallCount: null,
    failureCount: null,
    findingCount: 0,
  },
};

function records() {
  const lines = [
    responseLine(1, {
      type: "message",
      id: "msg-1",
      role: "user",
      content: [{ type: "input_text", text: "hello" }],
    }),
    responseLine(2, {
      type: "function_call",
      call_id: "c1",
      name: "exec_command",
      arguments: JSON.stringify({ cmd: "echo hi" }),
    }),
    responseLine(3, {
      type: "function_call_output",
      call_id: "c1",
      output: "Chunk ID: 1\nProcess exited with code 0\nOutput:\nhi\n",
    }),
    eventLine(4, {
      type: "item_completed",
      item: {
        type: "CommandExecution",
        id: "c1",
        command: ["/bin/zsh", "-lc", "echo hi"],
        cwd: "file:///tmp",
        parsed_cmd: [],
        status: "completed",
        aggregated_output: "hi\nProcess exited with code 0\n",
        process_id: "42",
      },
    }),
    eventLine(5, {
      type: "item_completed",
      item: {
        type: "FileChange",
        id: "fc1",
        changes: {
          "/tmp/a.ts": { type: "update", unified_diff: "@@ -1 +1 @@" },
        },
        status: "completed",
        stdout: "updated",
        stderr: "",
      },
    }),
    eventLine(6, {
      type: "item_completed",
      item: {
        type: "McpToolCall",
        id: "mcp1",
        server: "node_repl",
        tool: "js",
        arguments: { code: "1 + 1" },
        result: { content: [{ type: "text", text: "2" }] },
        status: "completed",
        duration: { secs: 0, nanos: 5000000 },
      },
    }),
    eventLine(7, {
      type: "item_completed",
      item: {
        type: "CollabAgentToolCall",
        id: "collab1",
        tool: "spawn_agent",
        status: "completed",
        sender_thread_id: "r",
        receiver_thread_ids: ["a"],
        receiver_agents: [{ thread_id: "a", agent_path: "/root/a" }],
        agents_states: { a: "running" },
      },
    }),
    eventLine(8, {
      type: "item_completed",
      item: {
        type: "SubAgentActivity",
        id: "sub1",
        kind: "started",
        agent_thread_id: "a",
        agent_path: "/root/a",
        model: "deepseek-v4-pro",
        reasoning_effort: "high",
      },
    }),
    tokenLine(9, {
      info: {
        last_token_usage: {
          input_tokens: 10,
          cached_input_tokens: 2,
          output_tokens: 5,
          total_tokens: 15,
        },
      },
    }),
    eventLine(10, { type: "task_aborted", turn_id: "t1" }),
    responseLine(11, {
      type: "agent_message",
      id: "amsg-1",
      author: "/root/a",
      recipient: "/root",
      content: [{ type: "input_text", text: "Message Type: FINAL_ANSWER\nPayload:\ndone" }],
    }),
    eventLine(12, {
      type: "item_completed",
      item: { type: "UserMessage", id: "msg-1", content: [{ type: "text", text: "hello" }] },
    }),
  ];
  return lines
    .map((line, index) => toRecord("r.jsonl", line, index + 1))
    .filter((record): record is NonNullable<typeof record> => record !== null);
}

describe("toTimelineItems", () => {
  it("maps commands, file changes, MCP, collaboration, tokens, and agent messages", () => {
    const items = toTimelineItems({ agent, records: records() });

    expect(items.map((item) => item.kind)).toEqual([
      "user-message",
      "command",
      "file-change",
      "mcp-call",
      "collab-call",
      "subagent-activity",
      "token-usage",
      "turn",
      "agent-communication",
    ]);
    expect(items.find((item) => item.kind === "command")?.details).toMatchObject({
      type: "command",
      command: ["/bin/zsh", "-lc", "echo hi"],
      processId: "42",
    });
    expect(items.find((item) => item.kind === "file-change")?.details).toMatchObject({
      type: "file-change",
      changes: [{ path: "/tmp/a.ts", changeType: "update", diff: "@@ -1 +1 @@" }],
    });
    expect(items.find((item) => item.kind === "collab-call")?.details).toMatchObject({
      type: "collab",
      receiverThreadIds: ["a"],
      receiverAgentPaths: ["/root/a"],
    });
    expect(items.find((item) => item.kind === "token-usage")?.details).toMatchObject({
      type: "token-usage",
      totalTokens: 15,
    });
    expect(items.find((item) => item.kind === "turn")?.status).toBe("aborted");
    expect(items.find((item) => item.kind === "agent-communication")?.details).toMatchObject({
      type: "message",
      author: "/root/a",
      recipient: "/root",
      messageType: "FINAL_ANSWER",
    });
  });

  it("keeps event-only agent messages instead of dropping them", () => {
    const record = toRecord(
      "r.jsonl",
      eventLine(1, {
        type: "item_completed",
        item: {
          type: "AgentMessage",
          id: "msg-2",
          content: [{ type: "Text", text: "event-only answer" }],
        },
      }),
      1,
    );
    if (!record) throw new Error("fixture record did not parse");

    const items = toTimelineItems({ agent, records: [record] });

    expect(items[0]).toMatchObject({
      kind: "agent-message",
      text: "event-only answer",
      details: { type: "message", role: "assistant" },
    });
  });
});
