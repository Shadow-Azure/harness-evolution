import { describe, expect, it } from "vitest";
import type { AgentNode } from "@harness/contracts";
import { responseLine } from "./fixtures";
import { toRecord } from "./meta";
import { extractSkillUses } from "./skills";

const agent: AgentNode = {
  threadId: "a",
  sessionId: "r",
  parentThreadId: "r",
  depth: 1,
  agentPath: "/root/a",
  nickname: "A",
  role: null,
  kind: "subagent",
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

function record(ordinal: number, command: string) {
  const parsed = toRecord(
    "a.jsonl",
    responseLine(ordinal, {
      type: "function_call",
      call_id: `call-${ordinal}`,
      name: "exec_command",
      arguments: JSON.stringify({ cmd: command }),
    }),
    ordinal + 1,
  );
  if (!parsed) throw new Error("fixture record did not parse");
  return parsed;
}

describe("extractSkillUses", () => {
  it("normalizes the same skill across different cache roots", () => {
    const records = [
      record(1, "cat /Users/a/.agents/skills/systematic-debugging/SKILL.md"),
      record(2, "cat /Users/a/.codex/.tmp/plugins/skills/Systematic-Debugging/SKILL.md"),
      record(3, "cat .agents/skills/pr-review-fix/SKILL.md"),
    ];

    const skills = extractSkillUses({ agent, records });

    expect(skills).toHaveLength(2);
    expect(skills[0]).toMatchObject({
      target: { type: "skill", id: "skill:pr-review-fix", name: "pr-review-fix" },
    });
    expect(skills[1]?.target.id).toBe("skill:systematic-debugging");
    expect(skills[1]?.occurrences).toHaveLength(2);
    expect(skills[1]?.occurrences[0]?.evidence).toMatchObject({
      rolloutId: "a.jsonl",
      ordinal: 1,
      callId: "call-1",
      agentThreadId: "a",
    });
  });
});
