import type {
  AgentNode,
  AttributionTarget,
  EvidenceRef,
  Finding,
  SessionFamily,
} from "@harness/contracts";
import type { ResolvedFinding, RolloutRecord, SnapshotSource } from "./types";
import { recordCallId, recordItemId, recordTurnId } from "./payload";

/**
 * Build a stable evidence anchor for one record.
 * @param agent Agent that produced the record.
 * @param record Parsed rollout record.
 * @param options Call ID, item ID, and excerpt overrides.
 * @returns Evidence anchor.
 */
export function evidenceForRecord(
  agent: AgentNode,
  record: RolloutRecord,
  options: {
    callId?: string | null;
    itemId?: string | null;
    excerpt: string;
  },
): EvidenceRef {
  return {
    id: `${record.rolloutId}#${record.ordinal}`,
    rolloutId: record.rolloutId,
    agentThreadId: agent.threadId,
    agentPath: agent.agentPath,
    ordinal: record.ordinal,
    line: record.line,
    recordType: record.type,
    turnId: recordTurnId(record),
    callId: options.callId ?? recordCallId(record),
    itemId: options.itemId ?? recordItemId(record),
    excerpt: options.excerpt.replace(/\s+/g, " ").trim().slice(0, 240),
  };
}

function resolveTarget(finding: Finding, family: SessionFamily): AttributionTarget {
  const target = finding.attribution.target;
  if (target.type === "agent") {
    const threadId = target.id.replace(/^agent:/, "");
    const agent = family.agents.find((candidate) => candidate.threadId === threadId);
    if (!agent) throw new Error(`agent target ${target.id} 不在家族 ${family.rootThreadId} 中`);
    return { ...target, name: target.name || agent.nickname || agent.agentPath };
  }
  if (!/^skill:[a-z0-9._-]+$/.test(target.id)) {
    throw new Error(`invalid skill target id: ${target.id}`);
  }
  return target;
}

/**
 * Resolve a finding's target and evidence anchors against a source.
 * @param input Finding, family, and source.
 * @returns Finding with evidence refreshed from the current records.
 */
export async function resolveFinding(input: {
  finding: Finding;
  family: SessionFamily;
  source: SnapshotSource;
}): Promise<ResolvedFinding> {
  if (input.finding.familyRootThreadId !== input.family.rootThreadId) {
    throw new Error(
      `finding ${input.finding.id} 属于 ${input.finding.familyRootThreadId}，不是 ${input.family.rootThreadId}`,
    );
  }
  const target = resolveTarget(input.finding, input.family);
  const evidence: EvidenceRef[] = [];
  for (const anchor of input.finding.evidence) {
    const agent = input.family.agents.find((candidate) =>
      candidate.segments.some((segment) => segment.rolloutId === anchor.rolloutId),
    );
    if (!agent) throw new Error(`evidence rollout ${anchor.rolloutId} 不在家族中`);
    const records = await input.source.readRecords(anchor.rolloutId);
    const record = records.find((candidate) => candidate.ordinal === anchor.ordinal);
    if (!record) {
      throw new Error(`evidence ordinal ${anchor.ordinal} 在 ${anchor.rolloutId} 中不存在`);
    }
    evidence.push(
      evidenceForRecord(agent, record, {
        callId: anchor.callId,
        itemId: anchor.itemId,
        excerpt: anchor.excerpt || record.type,
      }),
    );
  }
  return {
    finding: { ...input.finding, evidence },
    target,
    evidence,
  };
}
