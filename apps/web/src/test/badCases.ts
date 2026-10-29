import type { BadCase } from "@harness/contracts";

/**
 * Build one complete API-shaped problem for frontend tests.
 * @param overrides Fields to replace in the default problem.
 * @returns Complete problem fixture.
 */
export function badCaseFixture(
  overrides: Partial<BadCase> = {},
): BadCase {
  return {
    badCaseId: "case-00000001",
    sessionId: "root-1",
    sessionTitle: "分析 agent loop 与 LLM 层",
    badCaseType: "self",
    objectName: "deep-research",
    objectType: "skill",
    objectVersion: "1.0.0",
    anchor: { agentId: "agent-a", eventIndex: 0 },
    badCaseAgent: { sessionId: "root-1", agentId: "agent-a" },
    title: "缺少来源标注",
    reason:
      "skill 输出没有标注来源，汇总阶段无法回溯每条结论的出处。",
    metaData: null,
    degraded: false,
    diagnosticCode: null,
    analysis: {
      probeId: null,
      attributeType: null,
      displayState: "unanalyzed",
      result: null,
      status: "unanalyzed",
    },
    ...overrides,
  } as BadCase;
}
