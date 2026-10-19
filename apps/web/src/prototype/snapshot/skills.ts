import type { AgentNode, SkillUse } from "@harness/contracts";
import type { RolloutRecord } from "./types";
import { asRecord, asString, recordCallId, recordItemId } from "./payload";
import { evidenceForRecord } from "./evidence";

const SKILL_PATTERN = /([^/\s"'\\]+)\/SKILL\.md\b/g;

/**
 * Extract explicit SKILL.md reads from tool calls.
 * @param input Agent and records to inspect.
 * @returns Skill uses grouped by normalized skill name.
 */
export function extractSkillUses(input: {
  agent: AgentNode;
  records: readonly RolloutRecord[];
}): SkillUse[] {
  const uses = new Map<string, SkillUse>();
  for (const record of input.records) {
    if (record.type !== "response_item") continue;
    const payload = asRecord(record.payload);
    const itemType = asString(payload?.type);
    if (itemType !== "function_call" && itemType !== "custom_tool_call") continue;
    const command = asString(payload?.arguments) ?? asString(payload?.input);
    if (!command) continue;
    const callId = recordCallId(record);
    const itemId = recordItemId(record);
    for (const match of command.matchAll(SKILL_PATTERN)) {
      const name = match[1];
      const sourcePath = match[0];
      if (!name || !sourcePath) continue;
      const normalized = name.toLowerCase();
      const key = `${input.agent.threadId}:${normalized}`;
      const existing = uses.get(key) ?? {
        id: `skill-use:${input.agent.threadId}:${normalized}`,
        agentThreadId: input.agent.threadId,
        agentPath: input.agent.agentPath,
        target: { type: "skill" as const, id: `skill:${normalized}`, name },
        occurrences: [],
      };
      existing.occurrences.push({
        evidence: evidenceForRecord(input.agent, record, {
          callId,
          itemId,
          excerpt: sourcePath,
        }),
        sourcePath,
      });
      uses.set(key, existing);
    }
  }
  return [...uses.values()].sort((left, right) => left.target.name.localeCompare(right.target.name));
}
