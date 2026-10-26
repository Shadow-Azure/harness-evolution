import type { SessionTree } from "@harness/contracts";

const childCount = 60;

/**
 * Deterministic 61-Agent tree used only by development performance and
 * collapse regressions.
 */
export const demoStressTree = {
  sessionId: "demo-stress",
  agents: [
    {
      agentId: "main",
      parentAgentId: null,
      kind: "main",
      agentType: null,
      taskKind: null,
      spawnDepth: 0,
      label: "主会话 · 性能压测",
      desc: "性能压测主会话",
      lines: 13_492,
      messagesCount: 2_457,
      toolUseId: null,
      skillName: null,
      teamName: null,
      events: Array.from({ length: childCount }, (_, index) => ({
        kind: "agent" as const,
        line: index + 1,
        messageOffset: index,
        name: `Agent ${index + 1}`,
        desc: `性能子任务 ${index + 1}`,
        toolUseId: `stress-tool-${index + 1}`,
      })),
    },
    ...Array.from({ length: childCount }, (_, index) => ({
      agentId: `stress-agent-${index + 1}`,
      parentAgentId: "main",
      kind: "subagent" as const,
      agentType: "general-purpose",
      taskKind: null,
      spawnDepth: 1,
      label: `general-purpose · 性能子任务 ${index + 1}`,
      desc: `性能子任务 ${index + 1}`,
      lines: 40 + index,
      messagesCount: 30 + index,
      toolUseId: `stress-tool-${index + 1}`,
      skillName: null,
      teamName: null,
      events: [],
    })),
  ],
  badCases: [],
} satisfies SessionTree;
