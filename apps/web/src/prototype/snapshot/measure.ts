import type { AgentNode, AgentStats, SessionFamily } from "@harness/contracts";
import type { RolloutRecord, SnapshotSource } from "./types";
import {
  asRecord,
  asString,
  extractExitCode,
  isFailureOutput,
  recordTurnId,
} from "./payload";

/**
 * Count agent statistics from already-loaded records.
 * @param agent Agent whose segments classify the records.
 * @param records Records from the agent's primary and continuation segments.
 * @returns Updated agent statistics.
 */
export function countAgentStats(
  agent: AgentNode,
  records: readonly RolloutRecord[],
): AgentStats {
  const primaryIds = new Set(
    agent.segments.filter((segment) => segment.primary).map((segment) => segment.rolloutId),
  );
  const turns = new Set<string>();
  let recordCount = 0;
  let continuationRecordCount = 0;
  let toolCallCount = 0;
  let failureCount = 0;
  for (const record of records) {
    if (primaryIds.has(record.rolloutId)) recordCount += 1;
    else continuationRecordCount += 1;
    const turnId = recordTurnId(record);
    if (turnId) turns.add(turnId);
    const payload = asRecord(record.payload);
    const itemType = asString(payload?.type);
    if (
      record.type === "response_item" &&
      (itemType === "function_call" || itemType === "custom_tool_call")
    ) {
      toolCallCount += 1;
    }
    if (
      record.type === "response_item" &&
      (itemType === "function_call_output" || itemType === "custom_tool_call_output")
    ) {
      const output = asString(payload?.output) ?? "";
      const exitCode = extractExitCode(output);
      if (isFailureOutput(output) || (exitCode !== null && exitCode !== 0)) failureCount += 1;
    }
    if (record.type === "event_msg" && itemType === "item_completed") {
      const item = asRecord(payload?.item);
      const itemStatus = asString(item?.status);
      if (
        itemStatus === "failed" &&
        (asString(item?.type) === "CommandExecution" || asString(item?.type) === "McpToolCall")
      ) {
        failureCount += 1;
      }
    }
  }
  return {
    segmentCount: agent.segments.length,
    recordCount,
    continuationRecordCount,
    byteCount: agent.segments.reduce((sum, segment) => sum + segment.byteCount, 0),
    turnCount: turns.size,
    toolCallCount,
    failureCount,
    findingCount: agent.stats.findingCount,
  };
}

/**
 * Measure a family by reading every segment explicitly.
 * @param input Family and source.
 * @returns A new family with record counts and per-agent stats filled in.
 */
export async function measureFamily(input: {
  family: SessionFamily;
  source: SnapshotSource;
}): Promise<SessionFamily> {
  const agents: AgentNode[] = [];
  for (const agent of input.family.agents) {
    const records: RolloutRecord[] = [];
    for (const segment of agent.segments) {
      records.push(...(await input.source.readRecords(segment.rolloutId)));
    }
    agents.push({ ...agent, stats: countAgentStats(agent, records) });
  }
  return {
    ...input.family,
    agents,
    stats: {
      ...input.family.stats,
      rolloutCount: agents.length,
      segmentCount: agents.reduce((sum, agent) => sum + agent.stats.segmentCount, 0),
      recordCount: agents.reduce((sum, agent) => sum + (agent.stats.recordCount ?? 0), 0),
      continuationRecordCount: agents.reduce(
        (sum, agent) => sum + (agent.stats.continuationRecordCount ?? 0),
        0,
      ),
      byteCount: agents.reduce((sum, agent) => sum + agent.stats.byteCount, 0),
      maxDepth: agents.reduce((max, agent) => Math.max(max, agent.depth), 0),
      agentCount: agents.length,
    },
  };
}
