/** Stable identity of a rollout thread, taken from session_meta.payload.id. */
export type ThreadId = string;

/** Stable identity of a rollout file relative to the Codex sessions root. */
export type RolloutId = string;

/** Lifecycle status inferred from a rollout's turn events. */
export type AgentStatus = "running" | "completed" | "failed" | "aborted" | "unknown";

/** Kind of agent inside a session family. */
export type AgentKind = "root" | "subagent";

/** Severity used by the prototype's example findings. */
export type FindingSeverity = "P0" | "P1" | "P2" | "P3";

/** Category used to group prototype findings. */
export type FindingCategory =
  | "agent-orchestration"
  | "skill-usage"
  | "tool-failure"
  | "verification-gap";

/** Diagnostic emitted when the snapshot index encounters malformed or ambiguous input. */
export type SnapshotDiagnosticCode =
  | "missing-root"
  | "missing-parent"
  | "cycle"
  | "duplicate-root"
  | "invalid-meta"
  | "empty-rollout"
  | "unreadable-rollout";

/** A target that a finding can be attributed to. */
export interface AttributionTarget {
  /** Stable target kind. */
  type: "skill" | "agent";
  /** Stable ID: agent:<threadId> or skill:<normalizedName>. */
  id: string;
  /** Human-readable name. */
  name: string;
}

/** Evidence anchor that points back to one rollout record. */
export interface EvidenceRef {
  /** Stable anchor: <rolloutId>#<ordinal>. */
  id: string;
  /** Rollout file identity relative to the sessions root. */
  rolloutId: RolloutId;
  /** Agent that produced the record. */
  agentThreadId: ThreadId;
  /** Agent path at the time the record was produced. */
  agentPath: string;
  /** Original record ordinal inside the rollout file. */
  ordinal: number;
  /** One-based line number for display. */
  line: number;
  /** Original record type such as response_item or event_msg. */
  recordType: string;
  /** Turn ID when the record belongs to a turn. */
  turnId: string | null;
  /** Tool call ID for paired call and output records. */
  callId: string | null;
  /** Response item ID when available. */
  itemId: string | null;
  /** Short excerpt for list views. */
  excerpt: string;
}

/** One rollout file segment that belongs to an agent thread. */
export interface RolloutSegment {
  /** File identity relative to the sessions root. */
  rolloutId: RolloutId;
  /** Thread represented by the segment. */
  threadId: ThreadId;
  /** Session metadata timestamp. */
  startedAt: string;
  /** File size in bytes. */
  byteCount: number;
  /** Primary-segment record count; null until measured. */
  recordCount: number | null;
  /** Whether this is the primary segment for the thread. */
  primary: boolean;
}

/** Aggregate counts for one agent. */
export interface AgentStats {
  /** Number of rollout segments. */
  segmentCount: number;
  /** Primary-segment record count; null until measured. */
  recordCount: number | null;
  /** Record count from continuation segments; null until measured. */
  continuationRecordCount: number | null;
  /** Total bytes across segments. */
  byteCount: number;
  /** Distinct turn count; null until measured. */
  turnCount: number | null;
  /** Tool-call count; null until measured. */
  toolCallCount: number | null;
  /** Failed tool-call count; null until measured. */
  failureCount: number | null;
  /** Number of findings that mention this agent. */
  findingCount: number;
}

/** One agent node in a session family tree. */
export interface AgentNode {
  /** Stable thread identity. */
  threadId: ThreadId;
  /** Session identity retained for display only. */
  sessionId: string;
  /** Parent thread from source.subagent.thread_spawn.parent_thread_id. */
  parentThreadId: ThreadId | null;
  /** Depth from thread_spawn.depth, or derived from the parent chain. */
  depth: number;
  /** Agent path such as /root/review. */
  agentPath: string;
  /** Human-readable nickname. */
  nickname: string | null;
  /** Agent role when recorded. */
  role: string | null;
  /** Root or subagent. */
  kind: AgentKind;
  /** Primary segment followed by continuation segments. */
  segments: RolloutSegment[];
  /** Direct child thread IDs. */
  children: ThreadId[];
  /** Aggregate counts. */
  stats: AgentStats;
}

/** Aggregate counts for a session family. */
export interface FamilyStats {
  /** Unique thread count. */
  rolloutCount: number;
  /** Rollout file count, including continuation segments. */
  segmentCount: number;
  /** Primary-segment record count; null until measured. */
  recordCount: number | null;
  /** Continuation-segment record count; null until measured. */
  continuationRecordCount: number | null;
  /** Total bytes across segments. */
  byteCount: number;
  /** Maximum agent depth. */
  maxDepth: number;
  /** Number of agents in the family. */
  agentCount: number;
  /** Number of example findings attached to the family. */
  findingCount: number;
}

/** One skill use occurrence derived from an explicit SKILL.md read. */
export interface SkillUseOccurrence {
  /** Evidence pointing at the tool call that read the file. */
  evidence: EvidenceRef;
  /** Path used in the tool call. */
  sourcePath: string;
}

/** Aggregated skill usage for one agent. */
export interface SkillUse {
  /** Stable occurrence-group ID. */
  id: string;
  /** Agent that read the skill. */
  agentThreadId: ThreadId;
  /** Agent path at read time. */
  agentPath: string;
  /** Attribution target for the skill. */
  target: AttributionTarget;
  /** Every explicit read of the skill. */
  occurrences: SkillUseOccurrence[];
}

/** How a finding was attributed. */
export interface FindingAttribution {
  /** Skill or agent target. */
  target: AttributionTarget;
  /** Why this target was chosen. */
  reason: string;
  /** Evidence strength. */
  confidence: "confirmed" | "inferred" | "unknown";
  /** What remains unverified. */
  unverified: string | null;
}

/** Prototype finding shown in the family-level findings panel. */
export interface Finding {
  /** Stable finding ID. */
  id: string;
  /** Root thread this finding belongs to. */
  familyRootThreadId: ThreadId;
  /** Short title. */
  title: string;
  /** Non-technical summary. */
  summary: string;
  /** User-visible impact. */
  impact: string;
  /** Severity. */
  severity: FindingSeverity;
  /** Category. */
  category: FindingCategory;
  /** Agents that contributed evidence. */
  sourceAgentThreadIds: ThreadId[];
  /** Attribution explanation. */
  attribution: FindingAttribution;
  /** Evidence anchors. */
  evidence: EvidenceRef[];
  /** This is a hand-curated example, not a live model result. */
  status: "example";
}

/** Diagnostic emitted while building an index. */
export interface SnapshotDiagnostic {
  /** Machine-readable code. */
  code: SnapshotDiagnosticCode;
  /** Human-readable detail. */
  message: string;
  /** Related rollout file, when known. */
  rolloutId: RolloutId | null;
  /** Related thread, when known. */
  threadId: ThreadId | null;
}

/** Discriminator for timeline item kinds. */
export type TimelineItemKind =
  | "user-message"
  | "developer-message"
  | "agent-message"
  | "agent-communication"
  | "reasoning"
  | "tool-call"
  | "tool-output"
  | "command"
  | "file-change"
  | "mcp-call"
  | "collab-call"
  | "subagent-activity"
  | "web-search"
  | "image-view"
  | "context-compaction"
  | "turn"
  | "token-usage"
  | "error"
  | "other";

/** Kind-specific timeline details. */
export type TimelineItemDetails =
  | {
      type: "message";
      role: "user" | "developer" | "assistant";
      author: string | null;
      recipient: string | null;
      messageType: string | null;
    }
  | { type: "reasoning" }
  | {
      type: "tool";
      name: string;
      arguments: string | null;
      output: string | null;
      exitCode: number | null;
    }
  | {
      type: "command";
      command: string[];
      cwd: string | null;
      parsed: unknown;
      output: string;
      exitCode: number | null;
      processId: string | null;
    }
  | {
      type: "file-change";
      changes: Array<{
        path: string;
        changeType: string;
        diff: string | null;
      }>;
      status: string;
      stdout: string | null;
      stderr: string | null;
    }
  | {
      type: "mcp";
      server: string;
      tool: string;
      arguments: unknown;
      result: unknown;
      durationMs: number | null;
      status: string;
    }
  | {
      type: "collab";
      tool: string;
      senderThreadId: string;
      receiverThreadIds: string[];
      receiverAgentPaths: string[];
      agentsStates: unknown;
      status: string;
    }
  | {
      type: "subagent";
      agentThreadId: string;
      agentPath: string;
      activity: string;
      model: string | null;
      effort: string | null;
    }
  | { type: "web-search"; query: string; action: unknown }
  | { type: "image"; path: string }
  | { type: "context-compaction"; summary: string | null }
  | {
      type: "turn";
      event: "started" | "completed" | "aborted";
      error: string | null;
    }
  | {
      type: "token-usage";
      inputTokens: number;
      outputTokens: number;
      totalTokens: number;
      cachedInputTokens: number | null;
    }
  | { type: "other"; summary: string };

/** One normalized timeline item. */
export interface TimelineItem {
  /** Stable item ID: <rolloutId>#<ordinal>. */
  id: string;
  /** Agent that produced the item. */
  agentThreadId: ThreadId;
  /** Rollout file identity. */
  rolloutId: RolloutId;
  /** Turn ID when available. */
  turnId: string | null;
  /** Original record ordinal. */
  ordinal: number;
  /** Original record timestamp. */
  timestamp: string | null;
  /** Item kind. */
  kind: TimelineItemKind;
  /** Display title. */
  title: string;
  /** Full text or output for folding in the UI. */
  text: string | null;
  /** Paired tool call ID. */
  callId: string | null;
  /** Outcome. */
  status: "ok" | "error" | "aborted" | "unknown";
  /** Kind-specific fields. */
  details: TimelineItemDetails;
  /** Evidence anchor. */
  evidence: EvidenceRef;
}

/** A complete session family centered on one root thread. */
export interface SessionFamily {
  /** Root thread. */
  rootThreadId: ThreadId;
  /** Root session ID for display. */
  rootSessionId: string;
  /** Root agent path, normally "/". */
  rootAgentPath: string;
  /** Optional human label. */
  label: string | null;
  /** Agents in BFS order. */
  agents: AgentNode[];
  /** Example findings for this family. */
  findings: Finding[];
  /** Derived skill uses, populated after loading records. */
  skills: SkillUse[];
  /** Aggregate counts. */
  stats: FamilyStats;
  /** Diagnostics related to this family. */
  diagnostics: SnapshotDiagnostic[];
}

/** Serializable snapshot used by the M1 prototype. */
export interface SessionFamilySnapshot {
  /** Snapshot schema version. */
  version: 1;
  /** Generation timestamp. */
  generatedAt: string;
  /** Families in the snapshot. */
  families: SessionFamily[];
  /** Findings in the snapshot. */
  findings: Finding[];
}
