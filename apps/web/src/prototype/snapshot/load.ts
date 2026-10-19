import type { AgentStatus, SessionFamily } from "@harness/contracts";
import type { LoadedRollout, RolloutRecord, SnapshotSource } from "./types";
import { asRecord, asString } from "./payload";
import { countAgentStats } from "./measure";
import { extractSkillUses } from "./skills";
import { toTimelineItems } from "./timeline";

/**
 * Infer an agent status from turn lifecycle events.
 * @param records Loaded records.
 * @returns Agent status.
 */
export function inferAgentStatus(records: readonly RolloutRecord[]): AgentStatus {
  let started = false;
  let completed = false;
  let failed = false;
  let aborted = false;
  for (const record of records) {
    if (record.type !== "event_msg") continue;
    const payload = asRecord(record.payload);
    const eventType = asString(payload?.type);
    if (eventType === "task_started") started = true;
    if (eventType === "task_complete") {
      completed = true;
      if (payload?.error) failed = true;
    }
    if (eventType === "turn_aborted" || eventType === "task_aborted") aborted = true;
  }
  if (aborted) return "aborted";
  if (failed) return "failed";
  if (completed) return "completed";
  if (started) return "running";
  return "unknown";
}

/**
 * Load one agent's rollout records and timeline.
 * @param input Thread, family, source, and continuation flag.
 * @returns Loaded rollout with records, timeline, status, and stats.
 */
export async function loadRollout(input: {
  threadId: string;
  family: SessionFamily;
  source: SnapshotSource;
  includeContinuation?: boolean;
}): Promise<LoadedRollout> {
  const agent = input.family.agents.find((candidate) => candidate.threadId === input.threadId);
  if (!agent) {
    throw new Error(`agent ${input.threadId} 不在家族 ${input.family.rootThreadId} 中`);
  }
  const segments = input.includeContinuation
    ? agent.segments
    : agent.segments.filter((segment) => segment.primary);
  const records: RolloutRecord[] = [];
  for (const segment of segments) {
    records.push(...(await input.source.readRecords(segment.rolloutId)));
  }
  return {
    threadId: input.threadId,
    records,
    timeline: toTimelineItems({ agent, records }),
    status: inferAgentStatus(records),
    stats: countAgentStats(agent, records),
    skills: extractSkillUses({ agent, records }),
  };
}
