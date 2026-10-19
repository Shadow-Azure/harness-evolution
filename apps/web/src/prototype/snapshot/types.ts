import type {
  AgentStatus,
  AgentStats,
  AttributionTarget,
  EvidenceRef,
  Finding,
  SessionFamily,
  SkillUse,
  SnapshotDiagnostic,
  TimelineItem,
} from "@harness/contracts";

/** A rollout file discovered under the sessions root. */
export interface RolloutFileRef {
  /** File identity relative to the sessions root. */
  rolloutId: string;
  /** File size in bytes. */
  byteCount: number;
  /** Last modification time in ISO format. */
  modifiedAt: string;
}

/** Metadata parsed from the first session_meta record. */
export interface RolloutSessionMeta {
  /** Thread identity from payload.id. */
  threadId: string;
  /** Session identity from payload.session_id. */
  sessionId: string;
  /** Declared parent thread, including non-thread_spawn children. */
  declaredParentThreadId: string | null;
  /** Parent thread used for Session Family membership. */
  familyParentThreadId: string | null;
  /** Depth recorded by thread_spawn, or null when unknown. */
  depth: number | null;
  /** Agent path recorded by thread_spawn. */
  agentPath: string | null;
  /** Agent nickname. */
  nickname: string | null;
  /** Agent role. */
  role: string | null;
  /** Working directory recorded at session start. */
  cwd: string | null;
  /** Session start timestamp. */
  startedAt: string;
  /** Root, subagent, or guardian review thread. */
  kind: "root" | "subagent" | "review";
}

/** One parsed JSONL record. */
export interface RolloutRecord {
  /** Rollout file identity. */
  rolloutId: string;
  /** One-based line number. */
  line: number;
  /** Record ordinal from the JSONL payload. */
  ordinal: number;
  /** Record timestamp. */
  timestamp: string | null;
  /** Top-level record type. */
  type: string;
  /** Full original payload. */
  payload: unknown;
}

/** Source of rollout files; implemented by Node and memory adapters. */
export interface SnapshotSource {
  /** List every candidate rollout file. */
  listRollouts(): Promise<readonly RolloutFileRef[]>;
  /** Read only the first session_meta line of a rollout. */
  readMeta(rolloutId: string): Promise<RolloutSessionMeta>;
  /** Read every record of one rollout. */
  readRecords(rolloutId: string): Promise<readonly RolloutRecord[]>;
}

/** Result of building a family index. */
export interface FamilyIndex {
  /** Families in the requested root order. */
  families: readonly SessionFamily[];
  /** Families keyed by root thread. */
  byRootThreadId: ReadonlyMap<string, SessionFamily>;
  /** Diagnostics not attached to a specific family. */
  diagnostics: readonly SnapshotDiagnostic[];
}

/** A loaded rollout with normalized timeline items. */
export interface LoadedRollout {
  /** Thread that was loaded. */
  threadId: string;
  /** Raw records for the selected segments. */
  records: readonly RolloutRecord[];
  /** Normalized timeline items. */
  timeline: readonly TimelineItem[];
  /** Agent status inferred from turn events. */
  status: AgentStatus;
  /** Measured stats for the agent. */
  stats: AgentStats;
  /** Skill uses derived from this agent's records. */
  skills: SkillUse[];
}

/** A finding whose evidence anchors were resolved against a source. */
export interface ResolvedFinding {
  /** Finding with resolved evidence. */
  finding: Finding;
  /** Resolved attribution target. */
  target: AttributionTarget;
  /** Evidence resolved to current line numbers and excerpts. */
  evidence: readonly EvidenceRef[];
}
