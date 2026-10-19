import type {
  AgentNode,
  AgentStats,
  Finding,
  SessionFamily,
  SnapshotDiagnostic,
} from "@harness/contracts";
import type {
  FamilyIndex,
  RolloutFileRef,
  RolloutSessionMeta,
  SnapshotSource,
} from "./types";

interface SegmentEntry {
  file: RolloutFileRef;
  meta: RolloutSessionMeta;
}

interface ThreadGroup {
  meta: RolloutSessionMeta;
  segments: SegmentEntry[];
}

function mergeMeta(current: RolloutSessionMeta, next: RolloutSessionMeta): RolloutSessionMeta {
  return {
    ...current,
    declaredParentThreadId: current.declaredParentThreadId ?? next.declaredParentThreadId,
    familyParentThreadId: current.familyParentThreadId ?? next.familyParentThreadId,
    depth: current.depth ?? next.depth,
    agentPath: current.agentPath ?? next.agentPath,
    nickname: current.nickname ?? next.nickname,
    role: current.role ?? next.role,
    cwd: current.cwd ?? next.cwd,
    kind: current.kind === "root" && next.kind !== "root" ? next.kind : current.kind,
  };
}

function pickPrimary(segments: readonly SegmentEntry[]): SegmentEntry {
  return segments.reduce((best, current) => {
    if (current.file.byteCount > best.file.byteCount) return current;
    if (current.file.byteCount === best.file.byteCount && current.meta.startedAt < best.meta.startedAt) return current;
    return best;
  });
}

function initialStats(segments: readonly SegmentEntry[]): AgentStats {
  return {
    segmentCount: segments.length,
    recordCount: null,
    continuationRecordCount: null,
    byteCount: segments.reduce((sum, segment) => sum + segment.file.byteCount, 0),
    turnCount: null,
    toolCallCount: null,
    failureCount: null,
    findingCount: 0,
  };
}

function buildAgentNode(threadId: string, group: ThreadGroup): AgentNode {
  const primary = pickPrimary(group.segments);
  const ordered = [
    primary,
    ...group.segments
      .filter((segment) => segment !== primary)
      .sort((left, right) => left.meta.startedAt.localeCompare(right.meta.startedAt)),
  ];
  return {
    threadId,
    sessionId: group.meta.sessionId,
    parentThreadId: group.meta.familyParentThreadId,
    depth: group.meta.depth ?? 0,
    agentPath: group.meta.agentPath ?? "/",
    nickname: group.meta.nickname,
    role: group.meta.role,
    kind: group.meta.kind === "root" ? "root" : "subagent",
    segments: ordered.map((segment) => ({
      rolloutId: segment.file.rolloutId,
      threadId,
      startedAt: segment.meta.startedAt,
      byteCount: segment.file.byteCount,
      recordCount: null,
      primary: segment === primary,
    })),
    children: [],
    stats: initialStats(group.segments),
  };
}

/**
 * Build a session-family index from session metadata.
 * @param input Roots, source, and optional findings.
 * @returns Families keyed by root thread plus diagnostics.
 */
export async function buildFamilyIndex(input: {
  roots: readonly string[];
  source: SnapshotSource;
  findings?: readonly Finding[];
}): Promise<FamilyIndex> {
  const diagnostics: SnapshotDiagnostic[] = [];
  const rootIds = [...new Set(input.roots)];
  if (rootIds.length !== input.roots.length) {
    diagnostics.push({
      code: "duplicate-root",
      message: "roots 列表包含重复项，已去重",
      rolloutId: null,
      threadId: null,
    });
  }
  const files = await input.source.listRollouts();
  const groups = new Map<string, ThreadGroup>();
  for (const file of files) {
    try {
      const meta = await input.source.readMeta(file.rolloutId);
      const group = groups.get(meta.threadId);
      if (group) {
        group.segments.push({ file, meta });
        group.meta = mergeMeta(group.meta, meta);
      } else {
        groups.set(meta.threadId, { meta, segments: [{ file, meta }] });
      }
    } catch (error) {
      diagnostics.push({
        code: /empty/i.test(error instanceof Error ? error.message : String(error))
          ? "empty-rollout"
          : "invalid-meta",
        message: `${file.rolloutId}: ${error instanceof Error ? error.message : String(error)}`,
        rolloutId: file.rolloutId,
        threadId: null,
      });
    }
  }
  const nodes = new Map<string, AgentNode>();
  for (const [threadId, group] of groups) {
    if (group.meta.kind === "review") continue;
    nodes.set(threadId, buildAgentNode(threadId, group));
  }
  for (const node of nodes.values()) {
    if (!node.parentThreadId) continue;
    const parent = nodes.get(node.parentThreadId);
    if (!parent) {
      diagnostics.push({
        code: "missing-parent",
        message: `${node.threadId} 的父线程 ${node.parentThreadId} 不在索引中`,
        rolloutId: node.segments[0]?.rolloutId ?? null,
        threadId: node.threadId,
      });
      continue;
    }
    parent.children.push(node.threadId);
  }
  const families: SessionFamily[] = [];
  for (const rootId of rootIds) {
    const root = nodes.get(rootId);
    if (!root) {
      diagnostics.push({
        code: "missing-root",
        message: `root thread ${rootId} 不在索引中`,
        rolloutId: null,
        threadId: rootId,
      });
      continue;
    }
    const visited = new Set<string>();
    const queue = [rootId];
    const agentIds: string[] = [];
    while (queue.length > 0) {
      const threadId = queue.shift();
      if (!threadId || visited.has(threadId)) continue;
      visited.add(threadId);
      const node = nodes.get(threadId);
      if (!node) continue;
      agentIds.push(threadId);
      for (const child of node.children) {
        if (visited.has(child)) {
          diagnostics.push({
            code: "cycle",
            message: `${threadId} 的子线程 ${child} 形成环或重复`,
            rolloutId: null,
            threadId: child,
          });
          continue;
        }
        queue.push(child);
      }
    }
    const agents = agentIds
      .map((threadId) => nodes.get(threadId))
      .filter((node): node is AgentNode => node !== undefined);
    const rootNode = agents[0] ?? root;
    const familyFindings = (input.findings ?? []).filter(
      (finding) => finding.familyRootThreadId === rootId,
    );
    const findingCounts = new Map<string, number>();
    for (const finding of familyFindings) {
      for (const agentId of finding.sourceAgentThreadIds) {
        findingCounts.set(agentId, (findingCounts.get(agentId) ?? 0) + 1);
      }
    }
    const measuredAgents = agents.map((agent) => ({
      ...agent,
      stats: { ...agent.stats, findingCount: findingCounts.get(agent.threadId) ?? 0 },
    }));
    families.push({
      rootThreadId: rootId,
      rootSessionId: rootNode.sessionId,
      rootAgentPath: rootNode.agentPath,
      label: null,
      agents: measuredAgents,
      findings: familyFindings,
      skills: [],
      stats: {
        rolloutCount: measuredAgents.length,
        segmentCount: measuredAgents.reduce((sum, agent) => sum + agent.stats.segmentCount, 0),
        recordCount: null,
        continuationRecordCount: null,
        byteCount: measuredAgents.reduce((sum, agent) => sum + agent.stats.byteCount, 0),
        maxDepth: measuredAgents.reduce((max, agent) => Math.max(max, agent.depth), 0),
        agentCount: measuredAgents.length,
        findingCount: familyFindings.length,
      },
      diagnostics: diagnostics.filter(
        (diagnostic) =>
          diagnostic.threadId === null ||
          measuredAgents.some((agent) => agent.threadId === diagnostic.threadId),
      ),
    });
  }
  return {
    families,
    byRootThreadId: new Map(families.map((family) => [family.rootThreadId, family])),
    diagnostics,
  };
}
