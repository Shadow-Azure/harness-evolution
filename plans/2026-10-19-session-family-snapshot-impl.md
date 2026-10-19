# Session Family Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared Session Family contracts, a metadata-only local snapshot index, lazy rollout loading, skill derivation, timeline normalization, and four evidence-backed cross-agent example findings for issue #10.

**Architecture:** Contracts live in `packages/contracts`; the Node/browser-agnostic loader lives in `apps/web/src/prototype/snapshot` behind a `SnapshotSource` interface. The index reads only the first `session_meta` line of each rollout; full records are loaded per thread on demand. Raw JSONL stays local and never enters the repository.

**Tech Stack:** TypeScript 5.9, React 19 workspace, Vitest 3, Node 22 `fs/promises`, pnpm 10.

**Spec:** [plans/2026-10-19-session-family-snapshot-design.md](2026-10-19-session-family-snapshot-design.md)

## Global Constraints

- Node >= 22 and pnpm >= 10; do not add runtime dependencies.
- `threadId` is `session_meta.payload.id`; `sessionId` is display-only and must never be used as a map key.
- `rolloutId` is the path relative to `~/.codex/sessions`, using `/` separators.
- Guardian threads (`source.subagent.other`) are excluded from Session Family membership.
- A thread may have multiple rollout segments; exactly one segment is primary. `recordCount` counts primary segments and `continuationRecordCount` counts the rest.
- The index must not call `readRecords`; full records are loaded only by `loadRollout` or `measureFamily`.
- Raw JSONL must not be committed. Only synthetic or derived fixtures may enter the repository.
- Every exported declaration in `apps/*/src` and `packages/*/src` needs JSDoc; exported functions need `@param` for every parameter and `@returns` unless the return is void-like.
- Commit titles must contain `(#10)`.
- Do not add browser UI, Vite middleware, a REST API, SQLite, or model calls.
- Issue scope must be expanded to `plans/**`, `.agents/flow/**`, `.agents/notes/**`, `apps/web/package.json`, `apps/web/tsconfig.json`, and `pnpm-lock.yaml` before the PR diff gate runs.

## File Map

| File | Responsibility |
|---|---|
| `packages/contracts/src/session-family.ts` | Cross-package Session Family, finding, evidence, skill, and timeline contracts |
| `packages/contracts/src/index.ts` | Re-export the new contracts |
| `apps/web/src/prototype/snapshot/types.ts` | Loader-only source, record, index, and resolution types |
| `apps/web/src/prototype/snapshot/payload.ts` | Defensive payload accessors and text/exit-code helpers |
| `apps/web/src/prototype/snapshot/meta.ts` | JSONL record parsing and `session_meta` normalization |
| `apps/web/src/prototype/snapshot/memory-source.ts` | In-memory `SnapshotSource` with call counters |
| `apps/web/src/prototype/snapshot/node-source.ts` | Node filesystem `SnapshotSource` |
| `apps/web/src/prototype/snapshot/family-index.ts` | Metadata-only family index, segment grouping, tree diagnostics |
| `apps/web/src/prototype/snapshot/load.ts` | Lazy rollout loading and timeline construction |
| `apps/web/src/prototype/snapshot/measure.ts` | Explicit full-read statistics for acceptance checks |
| `apps/web/src/prototype/snapshot/skills.ts` | Explicit `SKILL.md` read extraction and path normalization |
| `apps/web/src/prototype/snapshot/timeline.ts` | JSONL record to `TimelineItem` mapping and deduplication |
| `apps/web/src/prototype/snapshot/evidence.ts` | Finding target and evidence resolution by ordinal |
| `apps/web/src/prototype/snapshot/findings.fixture.ts` | Four sanitized cross-agent example findings |
| `apps/web/src/prototype/snapshot/fixtures.ts` | Synthetic JSONL line builders shared by tests |

---

## Task 1: Shared contracts and a type-level smoke test

**Files:**
- Create: `packages/contracts/src/session-family.ts`
- Modify: `packages/contracts/src/index.ts`
- Create: `apps/web/src/prototype/snapshot/contracts.test.ts`

**Interfaces:**
- Consumes: existing `@harness/contracts` package and its `tsc --noEmit` script.
- Produces: `ThreadId`, `RolloutId`, `AgentStatus`, `AgentKind`, `FindingSeverity`, `FindingCategory`, `SnapshotDiagnosticCode`, `AttributionTarget`, `EvidenceRef`, `RolloutSegment`, `AgentStats`, `AgentNode`, `FamilyStats`, `SkillUseOccurrence`, `SkillUse`, `FindingAttribution`, `Finding`, `SnapshotDiagnostic`, `TimelineItemKind`, `TimelineItemDetails`, `TimelineItem`, `SessionFamily`, `SessionFamilySnapshot`.

- [ ] **Step 1: Write the failing type smoke test**

```ts
// apps/web/src/prototype/snapshot/contracts.test.ts
import { describe, expect, it } from "vitest";
import type { SessionFamily } from "@harness/contracts";

describe("session family contracts", () => {
  it("accepts the four-family snapshot shape", () => {
    const family = {
      rootThreadId: "root",
      rootSessionId: "session",
      rootAgentPath: "/",
      label: null,
      agents: [],
      findings: [],
      skills: [],
      stats: {
        rolloutCount: 0,
        segmentCount: 0,
        recordCount: null,
        continuationRecordCount: null,
        byteCount: 0,
        maxDepth: 0,
        agentCount: 0,
        findingCount: 0,
      },
      diagnostics: [],
    } satisfies SessionFamily;

    expect(family.stats.recordCount).toBeNull();
  });
});
```

- [ ] **Step 2: Run the typecheck to verify it fails**

Run: `pnpm --filter @harness/web typecheck`
Expected: FAIL because `@harness/contracts` does not export `SessionFamily`.

- [ ] **Step 3: Add the contracts**

Create `packages/contracts/src/session-family.ts`:

```ts
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
```

Keep the existing `ServicePhase` and `HealthResponse` declarations in `packages/contracts/src/index.ts` and append:

```ts
export type {
  AgentKind,
  AgentNode,
  AgentStats,
  AgentStatus,
  AttributionTarget,
  EvidenceRef,
  FamilyStats,
  Finding,
  FindingAttribution,
  FindingCategory,
  FindingSeverity,
  RolloutId,
  RolloutSegment,
  SessionFamily,
  SessionFamilySnapshot,
  SkillUse,
  SkillUseOccurrence,
  SnapshotDiagnostic,
  SnapshotDiagnosticCode,
  ThreadId,
  TimelineItem,
  TimelineItemDetails,
  TimelineItemKind,
} from "./session-family";
```

- [ ] **Step 4: Run the typecheck and smoke test**

Run: `pnpm --filter @harness/contracts typecheck && pnpm --filter @harness/web typecheck && pnpm --filter @harness/web exec vitest run src/prototype/snapshot/contracts.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/contracts/src/session-family.ts packages/contracts/src/index.ts apps/web/src/prototype/snapshot/contracts.test.ts
git commit -m "feat: 定义 Session Family 共享契约 (#10)"
```

---

## Task 2: Source types, metadata parsing, memory source, and fixtures

**Files:**
- Create: `apps/web/src/prototype/snapshot/types.ts`
- Create: `apps/web/src/prototype/snapshot/payload.ts`
- Create: `apps/web/src/prototype/snapshot/meta.ts`
- Create: `apps/web/src/prototype/snapshot/memory-source.ts`
- Create: `apps/web/src/prototype/snapshot/fixtures.ts`
- Create: `apps/web/src/prototype/snapshot/meta.test.ts`
- Create: `apps/web/src/prototype/snapshot/memory-source.test.ts`

**Interfaces:**
- Consumes: `SessionFamily`, `SnapshotDiagnostic`, `TimelineItem`, `Finding`, `AttributionTarget`, `AgentStats`, `EvidenceRef` from `@harness/contracts`.
- Produces: `RolloutFileRef`, `RolloutSessionMeta`, `RolloutRecord`, `SnapshotSource`, `MemorySnapshotSource`, `FamilyIndex`, `LoadedRollout`, `ResolvedFinding`, `createMemorySnapshotSource`, `parseSessionMeta`, `toRecord`, `asRecord`, `asString`, `asNumber`, `recordTurnId`, `recordCallId`, `recordItemId`, `extractContentText`, `extractExitCode`, `isFailureOutput`, `metaLine`, `responseLine`, `eventLine`, `tokenLine`.

- [ ] **Step 1: Write failing metadata and memory-source tests**

```ts
// apps/web/src/prototype/snapshot/meta.test.ts
import { describe, expect, it } from "vitest";
import { metaLine, responseLine } from "./fixtures";
import { parseSessionMeta, toRecord } from "./meta";

describe("session metadata", () => {
  it("keeps thread identity separate from a reused session id", () => {
    const meta = parseSessionMeta(
      metaLine({
        threadId: "child-thread",
        sessionId: "root-session",
        parentThreadId: "root-thread",
        depth: 2,
        agentPath: "/root/child",
        nickname: "Ada",
      }),
      "child.jsonl",
    );

    expect(meta).toMatchObject({
      threadId: "child-thread",
      sessionId: "root-session",
      familyParentThreadId: "root-thread",
      depth: 2,
      agentPath: "/root/child",
      nickname: "Ada",
      kind: "subagent",
    });
  });

  it("classifies guardian threads as review agents", () => {
    const meta = parseSessionMeta(
      metaLine({ threadId: "guardian", sessionId: "root-session", parentThreadId: "root-thread", other: "guardian" }),
      "guardian.jsonl",
    );

    expect(meta?.kind).toBe("review");
    expect(meta?.familyParentThreadId).toBeNull();
  });

  it("preserves line and ordinal for evidence anchors", () => {
    const record = toRecord("a.jsonl", responseLine(41, { type: "message", role: "user", content: [] }), 7);

    expect(record).toMatchObject({ rolloutId: "a.jsonl", line: 7, ordinal: 41, type: "response_item" });
  });
});
```

```ts
// apps/web/src/prototype/snapshot/memory-source.test.ts
import { describe, expect, it } from "vitest";
import { createMemorySnapshotSource } from "./memory-source";
import { metaLine, responseLine } from "./fixtures";

describe("memory snapshot source", () => {
  it("reads metadata without reading records", async () => {
    const source = createMemorySnapshotSource({
      "root.jsonl": [
        metaLine({ threadId: "root" }),
        responseLine(1, { type: "message", role: "user", content: [{ type: "input_text", text: "hello" }] }),
      ],
    });

    const files = await source.listRollouts();
    const meta = await source.readMeta("root.jsonl");

    expect(files).toHaveLength(1);
    expect(meta.threadId).toBe("root");
    expect(source.calls.readMeta).toBe(1);
    expect(source.calls.readRecords).toBe(0);
    expect(source.calls.metaRolloutIds).toEqual(["root.jsonl"]);
  });

  it("returns every record on demand", async () => {
    const source = createMemorySnapshotSource({
      "root.jsonl": [
        metaLine({ threadId: "root" }),
        responseLine(1, { type: "message", role: "user", content: [] }),
      ],
    });

    const records = await source.readRecords("root.jsonl");

    expect(records.map((record) => record.ordinal)).toEqual([0, 1]);
    expect(source.calls.readRecords).toBe(1);
    expect(source.calls.recordsRolloutIds).toEqual(["root.jsonl"]);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm --filter @harness/web exec vitest run src/prototype/snapshot/meta.test.ts src/prototype/snapshot/memory-source.test.ts`
Expected: FAIL because `./fixtures`, `./meta`, and `./memory-source` do not exist.

- [ ] **Step 3: Add the loader types and helpers**

Create `apps/web/src/prototype/snapshot/types.ts`:

```ts
import type {
  AgentStatus,
  AgentStats,
  AttributionTarget,
  EvidenceRef,
  Finding,
  SessionFamily,
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
```

Create `apps/web/src/prototype/snapshot/payload.ts`:

```ts
import type { RolloutRecord } from "./types";

/**
 * Narrow an unknown value to a non-array object.
 * @param value Value to inspect.
 * @returns Object record or null.
 */
export function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * Read a non-empty string.
 * @param value Value to inspect.
 * @returns String or null.
 */
export function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Read a finite number.
 * @param value Value to inspect.
 * @returns Number or null.
 */
export function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Extract a turn ID from a record.
 * @param record Parsed rollout record.
 * @returns Turn ID or null.
 */
export function recordTurnId(record: RolloutRecord): string | null {
  const payload = asRecord(record.payload);
  const internal = asRecord(payload?.internal_chat_message_metadata_passthrough);
  return asString(payload?.turn_id) ?? asString(payload?.root_turn_id) ?? asString(internal?.turn_id);
}

/**
 * Extract a tool call ID from a record.
 * @param record Parsed rollout record.
 * @returns Call ID or null.
 */
export function recordCallId(record: RolloutRecord): string | null {
  const payload = asRecord(record.payload);
  const item = asRecord(payload?.item);
  return asString(payload?.call_id) ?? asString(payload?.id) ?? asString(item?.id);
}

/**
 * Extract a response item ID from a record.
 * @param record Parsed rollout record.
 * @returns Item ID or null.
 */
export function recordItemId(record: RolloutRecord): string | null {
  const payload = asRecord(record.payload);
  const item = asRecord(payload?.item);
  return asString(payload?.id) ?? asString(item?.id);
}

/**
 * Flatten Codex content arrays into plain text.
 * @param value Content array, string, or content object.
 * @returns Joined text or null.
 */
export function extractContentText(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    const parts = value
      .map((entry) => {
        if (typeof entry === "string") return entry;
        const item = asRecord(entry);
        return asString(item?.text) ?? asString(item?.content);
      })
      .filter((part): part is string => part !== null);
    return parts.length > 0 ? parts.join("\n") : null;
  }
  const object = asRecord(value);
  return asString(object?.text) ?? asString(object?.content);
}

/**
 * Read a process exit code from command output.
 * @param output Tool output.
 * @returns Exit code or null when the output has none.
 */
export function extractExitCode(output: string): number | null {
  const match = /(?:Process exited with code|Exit code:)\s+(\d+)/i.exec(output);
  return match ? Number.parseInt(match[1] ?? "", 10) : null;
}

/**
 * Decide whether a tool output represents a failure.
 * @param output Tool output.
 * @returns True for non-zero exits and known failure signatures.
 */
export function isFailureOutput(output: string): boolean {
  const exitCode = extractExitCode(output);
  if (exitCode !== null && exitCode !== 0) return true;
  return /apply_patch verification failed|Failed to find expected lines|error connecting to api\.github\.com/i.test(output);
}
```

Create `apps/web/src/prototype/snapshot/meta.ts`:

```ts
import type { RolloutRecord, RolloutSessionMeta } from "./types";
import { asNumber, asRecord, asString } from "./payload";

/**
 * Parse one JSONL line into a rollout record.
 * @param rolloutId Rollout file identity.
 * @param line Raw JSONL line.
 * @param lineNumber One-based line number.
 * @returns Parsed record, or null when the line is not a JSON object.
 */
export function toRecord(rolloutId: string, line: string, lineNumber: number): RolloutRecord | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(line);
  } catch {
    return null;
  }
  const object = asRecord(parsed);
  if (!object) return null;
  return {
    rolloutId,
    line: lineNumber,
    ordinal: asNumber(object.ordinal) ?? lineNumber - 1,
    timestamp: asString(object.timestamp),
    type: asString(object.type) ?? "unknown",
    payload: object.payload ?? null,
  };
}

/**
 * Parse the first session_meta record of a rollout.
 * @param line Raw first JSONL line.
 * @param rolloutId Rollout file identity used in error messages.
 * @returns Normalized metadata, or null when the line is not session_meta.
 */
export function parseSessionMeta(line: string, rolloutId: string): RolloutSessionMeta | null {
  const record = toRecord(rolloutId, line, 1);
  if (!record || record.type !== "session_meta") return null;
  const payload = asRecord(record.payload);
  if (!payload) return null;
  const threadId = asString(payload.id);
  const sessionId = asString(payload.session_id) ?? threadId;
  if (!threadId || !sessionId) return null;
  const source = asRecord(payload.source);
  const subagent = asRecord(source?.subagent);
  const spawn = asRecord(subagent?.thread_spawn);
  const other = asString(subagent?.other);
  const familyParentThreadId = asString(spawn?.parent_thread_id);
  const kind: RolloutSessionMeta["kind"] = spawn ? "subagent" : other ? "review" : "root";
  return {
    threadId,
    sessionId,
    declaredParentThreadId: asString(payload.parent_thread_id),
    familyParentThreadId,
    depth: asNumber(spawn?.depth),
    agentPath: asString(spawn?.agent_path) ?? (kind === "root" ? "/" : null),
    nickname: asString(spawn?.agent_nickname),
    role: asString(spawn?.agent_role),
    cwd: asString(payload.cwd),
    startedAt: asString(payload.timestamp) ?? record.timestamp ?? "1970-01-01T00:00:00.000Z",
    kind,
  };
}
```

Create `apps/web/src/prototype/snapshot/memory-source.ts`:

```ts
import { parseSessionMeta, toRecord } from "./meta";
import type { RolloutFileRef, RolloutRecord, RolloutSessionMeta, SnapshotSource } from "./types";

/** In-memory source used by tests and fixtures. */
export interface MemorySnapshotSource extends SnapshotSource {
  /** Call counters used to prove lazy loading. */
  readonly calls: {
    /** Number of listRollouts calls. */
    listRollouts: number;
    /** Number of readMeta calls. */
    readMeta: number;
    /** Number of readRecords calls. */
    readRecords: number;
    /** Rollouts whose metadata was read. */
    metaRolloutIds: string[];
    /** Rollouts whose records were read. */
    recordsRolloutIds: string[];
  };
}

/**
 * Create a memory-backed snapshot source.
 * @param files Map of rolloutId to JSONL lines.
 * @returns Source with call counters for assertions.
 */
export function createMemorySnapshotSource(
  files: Record<string, readonly string[]>,
): MemorySnapshotSource {
  const encoder = new TextEncoder();
  const calls = {
    listRollouts: 0,
    readMeta: 0,
    readRecords: 0,
    metaRolloutIds: [] as string[],
    recordsRolloutIds: [] as string[],
  };
  const entries = Object.entries(files).sort(([left], [right]) => left.localeCompare(right));
  return {
    calls,
    async listRollouts(): Promise<readonly RolloutFileRef[]> {
      calls.listRollouts += 1;
      return entries.map(([rolloutId, lines]) => ({
        rolloutId,
        byteCount: lines.reduce((sum, line) => sum + encoder.encode(line).byteLength + 1, 0),
        modifiedAt: "2026-10-18T00:00:00.000Z",
      }));
    },
    async readMeta(rolloutId: string): Promise<RolloutSessionMeta> {
      calls.readMeta += 1;
      calls.metaRolloutIds.push(rolloutId);
      const lines = files[rolloutId];
      if (!lines || lines.length === 0) throw new Error(`empty rollout: ${rolloutId}`);
      const meta = parseSessionMeta(lines[0] ?? "", rolloutId);
      if (!meta) throw new Error(`invalid session_meta: ${rolloutId}`);
      return meta;
    },
    async readRecords(rolloutId: string): Promise<readonly RolloutRecord[]> {
      calls.readRecords += 1;
      calls.recordsRolloutIds.push(rolloutId);
      const lines = files[rolloutId];
      if (!lines) throw new Error(`missing rollout: ${rolloutId}`);
      return lines
        .map((line, index) => toRecord(rolloutId, line, index + 1))
        .filter((record): record is RolloutRecord => record !== null);
    },
  };
}
```

Create `apps/web/src/prototype/snapshot/fixtures.ts`:

```ts
/** Options for a synthetic session_meta line. */
export interface MetaLineOptions {
  /** Thread ID. */
  threadId: string;
  /** Session ID; defaults to the thread ID. */
  sessionId?: string;
  /** Declared parent thread. */
  parentThreadId?: string | null;
  /** Spawn depth. */
  depth?: number | null;
  /** Agent path. */
  agentPath?: string | null;
  /** Agent nickname. */
  nickname?: string | null;
  /** Non-spawn subagent kind such as guardian. */
  other?: string | null;
  /** Start timestamp. */
  timestamp?: string;
}

/**
 * Build a synthetic session_meta JSONL line.
 * @param options Metadata options.
 * @returns JSON string with one newline-free record.
 */
export function metaLine(options: MetaLineOptions): string {
  const timestamp = options.timestamp ?? "2026-10-18T00:00:00.000Z";
  const source =
    options.other !== undefined && options.other !== null
      ? { subagent: { other: options.other } }
      : options.parentThreadId
        ? {
            subagent: {
              thread_spawn: {
                parent_thread_id: options.parentThreadId,
                depth: options.depth ?? 1,
                agent_path: options.agentPath ?? "/root/child",
                agent_nickname: options.nickname ?? null,
                agent_role: null,
              },
            },
          }
        : "vscode";
  return JSON.stringify({
    timestamp,
    ordinal: 0,
    type: "session_meta",
    payload: {
      session_id: options.sessionId ?? options.threadId,
      id: options.threadId,
      parent_thread_id: options.parentThreadId ?? undefined,
      timestamp,
      cwd: "/tmp/workspace",
      source,
      thread_source: "user",
    },
  });
}

/**
 * Build a synthetic response_item JSONL line.
 * @param ordinal Record ordinal.
 * @param payload Response payload.
 * @param timestamp Record timestamp.
 * @returns JSON string.
 */
export function responseLine(
  ordinal: number,
  payload: Record<string, unknown>,
  timestamp = "2026-10-18T00:00:00.000Z",
): string {
  return JSON.stringify({ timestamp, ordinal, type: "response_item", payload });
}

/**
 * Build a synthetic event_msg JSONL line.
 * @param ordinal Record ordinal.
 * @param payload Event payload.
 * @param timestamp Record timestamp.
 * @returns JSON string.
 */
export function eventLine(
  ordinal: number,
  payload: Record<string, unknown>,
  timestamp = "2026-10-18T00:00:00.000Z",
): string {
  return JSON.stringify({ timestamp, ordinal, type: "event_msg", payload });
}

/**
 * Build a synthetic token_usage_record JSONL line.
 * @param ordinal Record ordinal.
 * @param payload Token payload.
 * @param timestamp Record timestamp.
 * @returns JSON string.
 */
export function tokenLine(
  ordinal: number,
  payload: Record<string, unknown>,
  timestamp = "2026-10-18T00:00:00.000Z",
): string {
  return JSON.stringify({ timestamp, ordinal, type: "token_usage_record", payload });
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm --filter @harness/web typecheck && pnpm --filter @harness/web exec vitest run src/prototype/snapshot/meta.test.ts src/prototype/snapshot/memory-source.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/prototype/snapshot/types.ts apps/web/src/prototype/snapshot/payload.ts apps/web/src/prototype/snapshot/meta.ts apps/web/src/prototype/snapshot/memory-source.ts apps/web/src/prototype/snapshot/fixtures.ts apps/web/src/prototype/snapshot/meta.test.ts apps/web/src/prototype/snapshot/memory-source.test.ts
git commit -m "feat: 解析 rollout 元数据并加入内存快照源 (#10)"
```

---

## Task 3: Metadata-only family index

**Files:**
- Create: `apps/web/src/prototype/snapshot/family-index.ts`
- Create: `apps/web/src/prototype/snapshot/family-index.test.ts`

**Interfaces:**
- Consumes: `SnapshotSource`, `RolloutFileRef`, `RolloutSessionMeta`, `createMemorySnapshotSource`, `metaLine`.
- Produces: `buildFamilyIndex(input: { roots: readonly string[]; source: SnapshotSource; findings?: readonly Finding[] }): Promise<FamilyIndex>`.

- [ ] **Step 1: Write the failing family-index tests**

```ts
// apps/web/src/prototype/snapshot/family-index.test.ts
import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { metaLine } from "./fixtures";
import { createMemorySnapshotSource } from "./memory-source";

function familySource() {
  return createMemorySnapshotSource({
    "root-cont.jsonl": [metaLine({ threadId: "r", timestamp: "2026-10-18T01:00:00.000Z" })],
    "root.jsonl": [metaLine({ threadId: "r" })],
    "a.jsonl": [
      metaLine({
        threadId: "a",
        sessionId: "r",
        parentThreadId: "r",
        depth: 1,
        agentPath: "/root/a",
        nickname: "A",
      }),
    ],
    "b.jsonl": [
      metaLine({
        threadId: "b",
        sessionId: "r",
        parentThreadId: "r",
        depth: 1,
        agentPath: "/root/b",
        nickname: "B",
      }),
    ],
    "c.jsonl": [
      metaLine({
        threadId: "c",
        sessionId: "r",
        parentThreadId: "a",
        depth: 2,
        agentPath: "/root/a/c",
        nickname: "C",
      }),
    ],
    "guardian.jsonl": [
      metaLine({ threadId: "g", sessionId: "r", parentThreadId: "r", other: "guardian" }),
    ],
    "unrelated.jsonl": [metaLine({ threadId: "u" })],
  });
}

describe("buildFamilyIndex", () => {
  it("builds the tree, groups segments, and excludes guardian threads", async () => {
    const source = familySource();
    const index = await buildFamilyIndex({ roots: ["r"], source });
    const family = index.families[0];

    expect(family).toBeDefined();
    expect(family?.agents.map((agent) => agent.threadId)).toEqual(["r", "a", "b", "c"]);
    expect(family?.agents.find((agent) => agent.threadId === "g")).toBeUndefined();
    expect(family?.agents.find((agent) => agent.threadId === "r")?.segments).toHaveLength(2);
    expect(family?.agents.find((agent) => agent.threadId === "r")?.segments.filter((segment) => segment.primary)).toHaveLength(1);
    expect(family?.stats.rolloutCount).toBe(4);
    expect(family?.stats.segmentCount).toBe(5);
    expect(family?.stats.maxDepth).toBe(2);
    expect(source.calls.readRecords).toBe(0);
  });

  it("does not let a reused session id overwrite another agent", async () => {
    const index = await buildFamilyIndex({ roots: ["r"], source: familySource() });
    const family = index.families[0];
    const a = family?.agents.find((agent) => agent.threadId === "a");
    const b = family?.agents.find((agent) => agent.threadId === "b");

    expect(a?.sessionId).toBe("r");
    expect(b?.sessionId).toBe("r");
    expect(a?.threadId).not.toBe(b?.threadId);
  });

  it("reports a missing root without throwing", async () => {
    const index = await buildFamilyIndex({ roots: ["missing"], source: familySource() });

    expect(index.families).toHaveLength(0);
    expect(index.diagnostics).toContainEqual(
      expect.objectContaining({ code: "missing-root", threadId: "missing" }),
    );
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm --filter @harness/web exec vitest run src/prototype/snapshot/family-index.test.ts`
Expected: FAIL because `./family-index` does not exist.

- [ ] **Step 3: Implement the family index**

Create `apps/web/src/prototype/snapshot/family-index.ts`:

```ts
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm --filter @harness/web typecheck && pnpm --filter @harness/web exec vitest run src/prototype/snapshot/family-index.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/prototype/snapshot/family-index.ts apps/web/src/prototype/snapshot/family-index.test.ts
git commit -m "feat: 建立 Session Family 元数据索引 (#10)"
```

---

## Task 4: Evidence anchors and explicit skill extraction

**Files:**
- Create: `apps/web/src/prototype/snapshot/evidence.ts`
- Create: `apps/web/src/prototype/snapshot/skills.ts`
- Create: `apps/web/src/prototype/snapshot/skills.test.ts`

**Interfaces:**
- Consumes: `AgentNode`, `EvidenceRef`, `SkillUse` from `@harness/contracts`; `RolloutRecord`, `toRecord`, `responseLine`.
- Produces: `evidenceForRecord(agent, record, options): EvidenceRef`, `extractSkillUses(input: { agent: AgentNode; records: readonly RolloutRecord[] }): SkillUse[]`.

- [ ] **Step 1: Write the failing skill extraction test**

```ts
// apps/web/src/prototype/snapshot/skills.test.ts
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter @harness/web exec vitest run src/prototype/snapshot/skills.test.ts`
Expected: FAIL because `./skills` does not exist.

- [ ] **Step 3: Implement evidence anchors and skill extraction**

Create `apps/web/src/prototype/snapshot/evidence.ts`:

```ts
import type { AgentNode, EvidenceRef } from "@harness/contracts";
import type { RolloutRecord } from "./types";
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
```

Create `apps/web/src/prototype/snapshot/skills.ts`:

```ts
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm --filter @harness/web typecheck && pnpm --filter @harness/web exec vitest run src/prototype/snapshot/skills.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/prototype/snapshot/evidence.ts apps/web/src/prototype/snapshot/skills.ts apps/web/src/prototype/snapshot/skills.test.ts
git commit -m "feat: 从 SKILL.md 读取派生 skill 使用 (#10)"
```

---

## Task 5: Timeline normalization and deduplication

**Files:**
- Create: `apps/web/src/prototype/snapshot/timeline.ts`
- Create: `apps/web/src/prototype/snapshot/timeline.test.ts`

**Interfaces:**
- Consumes: `AgentNode`, `TimelineItem`, `TimelineItemDetails`, `TimelineItemKind` from `@harness/contracts`; `RolloutRecord`, `evidenceForRecord`, payload helpers.
- Produces: `toTimelineItems(input: { agent: AgentNode; records: readonly RolloutRecord[] }): TimelineItem[]`.

- [ ] **Step 1: Write the failing timeline test**

```ts
// apps/web/src/prototype/snapshot/timeline.test.ts
import { describe, expect, it } from "vitest";
import type { AgentNode } from "@harness/contracts";
import { eventLine, responseLine, tokenLine } from "./fixtures";
import { toRecord } from "./meta";
import { toTimelineItems } from "./timeline";

const agent: AgentNode = {
  threadId: "r",
  sessionId: "r",
  parentThreadId: null,
  depth: 0,
  agentPath: "/",
  nickname: null,
  role: null,
  kind: "root",
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

function records() {
  const lines = [
    responseLine(1, {
      type: "message",
      id: "msg-1",
      role: "user",
      content: [{ type: "input_text", text: "hello" }],
    }),
    responseLine(2, {
      type: "function_call",
      call_id: "c1",
      name: "exec_command",
      arguments: JSON.stringify({ cmd: "echo hi" }),
    }),
    responseLine(3, {
      type: "function_call_output",
      call_id: "c1",
      output: "Chunk ID: 1\nProcess exited with code 0\nOutput:\nhi\n",
    }),
    eventLine(4, {
      type: "item_completed",
      item: {
        type: "CommandExecution",
        id: "c1",
        command: ["/bin/zsh", "-lc", "echo hi"],
        cwd: "file:///tmp",
        parsed_cmd: [],
        status: "completed",
        aggregated_output: "hi\nProcess exited with code 0\n",
        process_id: "42",
      },
    }),
    eventLine(5, {
      type: "item_completed",
      item: {
        type: "FileChange",
        id: "fc1",
        changes: {
          "/tmp/a.ts": { type: "update", unified_diff: "@@ -1 +1 @@" },
        },
        status: "completed",
        stdout: "updated",
        stderr: "",
      },
    }),
    eventLine(6, {
      type: "item_completed",
      item: {
        type: "McpToolCall",
        id: "mcp1",
        server: "node_repl",
        tool: "js",
        arguments: { code: "1 + 1" },
        result: { content: [{ type: "text", text: "2" }] },
        status: "completed",
        duration: { secs: 0, nanos: 5000000 },
      },
    }),
    eventLine(7, {
      type: "item_completed",
      item: {
        type: "CollabAgentToolCall",
        id: "collab1",
        tool: "spawn_agent",
        status: "completed",
        sender_thread_id: "r",
        receiver_thread_ids: ["a"],
        receiver_agents: [{ thread_id: "a", agent_path: "/root/a" }],
        agents_states: { a: "running" },
      },
    }),
    eventLine(8, {
      type: "item_completed",
      item: {
        type: "SubAgentActivity",
        id: "sub1",
        kind: "started",
        agent_thread_id: "a",
        agent_path: "/root/a",
        model: "deepseek-v4-pro",
        reasoning_effort: "high",
      },
    }),
    tokenLine(9, {
      info: {
        last_token_usage: {
          input_tokens: 10,
          cached_input_tokens: 2,
          output_tokens: 5,
          total_tokens: 15,
        },
      },
    }),
    eventLine(10, { type: "task_aborted", turn_id: "t1" }),
    responseLine(11, {
      type: "agent_message",
      id: "amsg-1",
      author: "/root/a",
      recipient: "/root",
      content: [{ type: "input_text", text: "Message Type: FINAL_ANSWER\nPayload:\ndone" }],
    }),
    eventLine(12, {
      type: "item_completed",
      item: { type: "UserMessage", id: "msg-1", content: [{ type: "text", text: "hello" }] },
    }),
  ];
  return lines
    .map((line, index) => toRecord("r.jsonl", line, index + 1))
    .filter((record): record is NonNullable<typeof record> => record !== null);
}

describe("toTimelineItems", () => {
  it("maps commands, file changes, MCP, collaboration, tokens, and agent messages", () => {
    const items = toTimelineItems({ agent, records: records() });

    expect(items.map((item) => item.kind)).toEqual([
      "user-message",
      "command",
      "file-change",
      "mcp-call",
      "collab-call",
      "subagent-activity",
      "token-usage",
      "turn",
      "agent-communication",
    ]);
    expect(items.find((item) => item.kind === "command")?.details).toMatchObject({
      type: "command",
      command: ["/bin/zsh", "-lc", "echo hi"],
      processId: "42",
    });
    expect(items.find((item) => item.kind === "file-change")?.details).toMatchObject({
      type: "file-change",
      changes: [{ path: "/tmp/a.ts", changeType: "update", diff: "@@ -1 +1 @@" }],
    });
    expect(items.find((item) => item.kind === "collab-call")?.details).toMatchObject({
      type: "collab",
      receiverThreadIds: ["a"],
      receiverAgentPaths: ["/root/a"],
    });
    expect(items.find((item) => item.kind === "token-usage")?.details).toMatchObject({
      type: "token-usage",
      totalTokens: 15,
    });
    expect(items.find((item) => item.kind === "turn")?.status).toBe("aborted");
    expect(items.find((item) => item.kind === "agent-communication")?.details).toMatchObject({
      type: "message",
      author: "/root/a",
      recipient: "/root",
      messageType: "FINAL_ANSWER",
    });
  });

  it("keeps event-only agent messages instead of dropping them", () => {
    const record = toRecord(
      "r.jsonl",
      eventLine(1, {
        type: "item_completed",
        item: {
          type: "AgentMessage",
          id: "msg-2",
          content: [{ type: "Text", text: "event-only answer" }],
        },
      }),
      1,
    );
    if (!record) throw new Error("fixture record did not parse");

    const items = toTimelineItems({ agent, records: [record] });

    expect(items[0]).toMatchObject({
      kind: "agent-message",
      text: "event-only answer",
      details: { type: "message", role: "assistant" },
    });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter @harness/web exec vitest run src/prototype/snapshot/timeline.test.ts`
Expected: FAIL because `./timeline` does not exist.

- [ ] **Step 3: Implement timeline normalization**

Create `apps/web/src/prototype/snapshot/timeline.ts`:

```ts
import type {
  AgentNode,
  TimelineItem,
  TimelineItemDetails,
  TimelineItemKind,
} from "@harness/contracts";
import type { RolloutRecord } from "./types";
import { evidenceForRecord } from "./evidence";
import {
  asNumber,
  asRecord,
  asString,
  extractContentText,
  extractExitCode,
  isFailureOutput,
  recordCallId,
  recordItemId,
  recordTurnId,
} from "./payload";

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((entry): entry is string => typeof entry === "string")
    : [];
}

function messageType(text: string | null): string | null {
  return text ? (/(?:^|\n)Message Type:\s*([A-Z_]+)/.exec(text)?.[1] ?? null) : null;
}

function durationMs(value: unknown): number | null {
  const duration = asRecord(value);
  if (!duration) return null;
  const secs = asNumber(duration.secs) ?? 0;
  const nanos = asNumber(duration.nanos) ?? 0;
  return Math.round(secs * 1000 + nanos / 1_000_000);
}

function makeItem(input: {
  agent: AgentNode;
  record: RolloutRecord;
  kind: TimelineItemKind;
  title: string;
  text: string | null;
  callId: string | null;
  status: TimelineItem["status"];
  details: TimelineItemDetails;
  itemId?: string | null;
}): TimelineItem {
  return {
    id: `${input.record.rolloutId}#${input.record.ordinal}`,
    agentThreadId: input.agent.threadId,
    rolloutId: input.record.rolloutId,
    turnId: recordTurnId(input.record),
    ordinal: input.record.ordinal,
    timestamp: input.record.timestamp,
    kind: input.kind,
    title: input.title,
    text: input.text,
    callId: input.callId,
    status: input.status,
    details: input.details,
    evidence: evidenceForRecord(input.agent, input.record, {
      callId: input.callId,
      itemId: input.itemId ?? recordItemId(input.record),
      excerpt: input.text ?? input.title,
    }),
  };
}

/**
 * Normalize rollout records into timeline items.
 * @param input Agent and parsed records.
 * @returns Ordered timeline items with duplicate UI events removed.
 */
export function toTimelineItems(input: {
  agent: AgentNode;
  records: readonly RolloutRecord[];
}): TimelineItem[] {
  const responseIds = new Set<string>();
  const commandCallIds = new Set<string>();
  for (const record of input.records) {
    if (record.type === "response_item") {
      const itemId = recordItemId(record);
      if (itemId) responseIds.add(itemId);
    }
    if (record.type === "event_msg") {
      const payload = asRecord(record.payload);
      const item = asRecord(payload?.item);
      if (asString(payload?.type) === "item_completed" && asString(item?.type) === "CommandExecution") {
        const callId = asString(item?.id);
        if (callId) commandCallIds.add(callId);
      }
    }
  }
  const items: TimelineItem[] = [];
  for (const record of input.records) {
    const payload = asRecord(record.payload);
    const eventType = asString(payload?.type);
    if (
      record.type === "session_meta" ||
      record.type === "turn_context" ||
      record.type === "world_state" ||
      record.type === "inter_agent_communication_metadata"
    ) {
      continue;
    }
    if (record.type === "response_item") {
      const itemType = asString(payload?.type);
      if (!itemType) continue;
      if (itemType === "function_call" || itemType === "custom_tool_call") {
        const callId = recordCallId(record);
        if (callId && commandCallIds.has(callId)) continue;
        const name = asString(payload?.name) ?? "tool";
        const text = asString(payload?.arguments) ?? asString(payload?.input);
        items.push(
          makeItem({
            agent: input.agent,
            record,
            kind: "tool-call",
            title: name,
            text,
            callId,
            status: "ok",
            details: { type: "tool", name, arguments: text, output: null, exitCode: null },
          }),
        );
        continue;
      }
      if (itemType === "function_call_output" || itemType === "custom_tool_call_output") {
        const callId = recordCallId(record);
        if (callId && commandCallIds.has(callId)) continue;
        const output = asString(payload?.output) ?? "";
        const exitCode = extractExitCode(output);
        items.push(
          makeItem({
            agent: input.agent,
            record,
            kind: "tool-output",
            title: "tool output",
            text: output,
            callId,
            status: isFailureOutput(output) ? "error" : "ok",
            details: { type: "tool", name: "", arguments: null, output, exitCode },
          }),
        );
        continue;
      }
      if (itemType === "message") {
        const role = asString(payload?.role);
        const kind: TimelineItemKind =
          role === "user" ? "user-message" : role === "developer" ? "developer-message" : "agent-message";
        const text = extractContentText(payload?.content);
        items.push(
          makeItem({
            agent: input.agent,
            record,
            kind,
            title: kind,
            text,
            callId: null,
            status: "ok",
            details: {
              type: "message",
              role: role === "user" || role === "developer" ? role : "assistant",
              author: null,
              recipient: null,
              messageType: null,
            },
          }),
        );
        continue;
      }
      if (itemType === "reasoning") {
        const text =
          extractContentText(payload?.summary) ?? extractContentText(payload?.content);
        items.push(
          makeItem({
            agent: input.agent,
            record,
            kind: "reasoning",
            title: "reasoning",
            text,
            callId: null,
            status: "ok",
            details: { type: "reasoning" },
          }),
        );
        continue;
      }
      if (itemType === "agent_message") {
        const text = extractContentText(payload?.content);
        items.push(
          makeItem({
            agent: input.agent,
            record,
            kind: "agent-communication",
            title: "agent message",
            text,
            callId: null,
            status: "ok",
            details: {
              type: "message",
              role: "assistant",
              author: asString(payload?.author),
              recipient: asString(payload?.recipient),
              messageType: asString(payload?.message_type) ?? messageType(text),
            },
          }),
        );
        continue;
      }
      if (itemType === "web_search_call") {
        const query = asString(payload?.query) ?? "";
        items.push(
          makeItem({
            agent: input.agent,
            record,
            kind: "web-search",
            title: "web search",
            text: query,
            callId: null,
            status: "ok",
            details: { type: "web-search", query, action: payload?.action ?? null },
          }),
        );
        continue;
      }
      items.push(
        makeItem({
          agent: input.agent,
          record,
          kind: "other",
          title: itemType,
          text: null,
          callId: null,
          status: "unknown",
          details: { type: "other", summary: itemType },
        }),
      );
      continue;
    }
    if (record.type === "event_msg") {
      if (eventType === "item_completed") {
        const item = asRecord(payload?.item);
        const itemType = asString(item?.type);
        const itemId = asString(item?.id);
        if (!itemType) continue;
        if (
          itemId &&
          responseIds.has(itemId) &&
          (itemType === "UserMessage" || itemType === "AgentMessage" || itemType === "Reasoning")
        ) {
          continue;
        }
        if (itemType === "UserMessage" || itemType === "AgentMessage") {
          const text = extractContentText(item?.content);
          const kind: TimelineItemKind = itemType === "UserMessage" ? "user-message" : "agent-message";
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind,
              title: kind,
              text,
              callId: null,
              status: "ok",
              details: {
                type: "message",
                role: itemType === "UserMessage" ? "user" : "assistant",
                author: null,
                recipient: null,
                messageType: null,
              },
            }),
          );
          continue;
        }
        if (itemType === "Reasoning") {
          const text =
            extractContentText(item?.summary_text) ?? extractContentText(item?.raw_content);
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind: "reasoning",
              title: "reasoning",
              text,
              callId: null,
              status: "ok",
              details: { type: "reasoning" },
            }),
          );
          continue;
        }
        if (itemType === "CommandExecution") {
          const output = asString(item?.aggregated_output) ?? "";
          const exitCode = extractExitCode(output);
          const callId = asString(item?.id);
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind: "command",
              title: "command",
              text: output,
              callId,
              status: isFailureOutput(output) || asString(item?.status) === "failed" ? "error" : "ok",
              details: {
                type: "command",
                command: stringArray(item?.command),
                cwd: asString(item?.cwd),
                parsed: item?.parsed_cmd ?? null,
                output,
                exitCode,
                processId: asString(item?.process_id),
              },
            }),
          );
          continue;
        }
        if (itemType === "FileChange") {
          const changes = asRecord(item?.changes) ?? {};
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind: "file-change",
              title: "file change",
              text: asString(item?.stdout),
              callId: null,
              status: asString(item?.status) === "failed" ? "error" : "ok",
              details: {
                type: "file-change",
                changes: Object.entries(changes).map(([path, value]) => {
                  const change = asRecord(value);
                  return {
                    path,
                    changeType: asString(change?.type) ?? "unknown",
                    diff: asString(change?.unified_diff),
                  };
                }),
                status: asString(item?.status) ?? "unknown",
                stdout: asString(item?.stdout),
                stderr: asString(item?.stderr),
              },
            }),
          );
          continue;
        }
        if (itemType === "McpToolCall") {
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind: "mcp-call",
              title: `${asString(item?.server) ?? "mcp"}/${asString(item?.tool) ?? "tool"}`,
              text: null,
              callId: asString(item?.id),
              status: asString(item?.status) === "failed" ? "error" : "ok",
              details: {
                type: "mcp",
                server: asString(item?.server) ?? "unknown",
                tool: asString(item?.tool) ?? "unknown",
                arguments: item?.arguments ?? null,
                result: item?.result ?? null,
                durationMs: durationMs(item?.duration),
                status: asString(item?.status) ?? "unknown",
              },
            }),
          );
          continue;
        }
        if (itemType === "CollabAgentToolCall") {
          const receiverAgents = Array.isArray(item?.receiver_agents) ? item.receiver_agents : [];
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind: "collab-call",
              title: asString(item?.tool) ?? "collab",
              text: null,
              callId: asString(item?.id),
              status: asString(item?.status) === "failed" ? "error" : "ok",
              details: {
                type: "collab",
                tool: asString(item?.tool) ?? "unknown",
                senderThreadId: asString(item?.sender_thread_id) ?? input.agent.threadId,
                receiverThreadIds: stringArray(item?.receiver_thread_ids),
                receiverAgentPaths: receiverAgents
                  .map((entry) => asString(asRecord(entry)?.agent_path))
                  .filter((path): path is string => path !== null),
                agentsStates: item?.agents_states ?? null,
                status: asString(item?.status) ?? "unknown",
              },
            }),
          );
          continue;
        }
        if (itemType === "SubAgentActivity") {
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind: "subagent-activity",
              title: `${asString(item?.kind) ?? "activity"} ${asString(item?.agent_path) ?? ""}`.trim(),
              text: null,
              callId: asString(item?.id),
              status: "ok",
              details: {
                type: "subagent",
                agentThreadId: asString(item?.agent_thread_id) ?? "",
                agentPath: asString(item?.agent_path) ?? "",
                activity: asString(item?.kind) ?? "unknown",
                model: asString(item?.model),
                effort: asString(item?.reasoning_effort),
              },
            }),
          );
          continue;
        }
        if (itemType === "WebSearch") {
          const query = asString(item?.query) ?? "";
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind: "web-search",
              title: "web search",
              text: query,
              callId: asString(item?.id),
              status: "ok",
              details: { type: "web-search", query, action: item?.action ?? null },
            }),
          );
          continue;
        }
        if (itemType === "ImageView") {
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind: "image-view",
              title: "image view",
              text: asString(item?.path),
              callId: asString(item?.id),
              status: "ok",
              details: { type: "image", path: asString(item?.path) ?? "" },
            }),
          );
          continue;
        }
        if (itemType === "ContextCompaction") {
          items.push(
            makeItem({
              agent: input.agent,
              record,
              kind: "context-compaction",
              title: "context compaction",
              text: asString(item?.message) ?? asString(item?.summary),
              callId: asString(item?.id),
              status: "ok",
              details: {
                type: "context-compaction",
                summary: asString(item?.summary) ?? asString(item?.message),
              },
            }),
          );
          continue;
        }
        items.push(
          makeItem({
            agent: input.agent,
            record,
            kind: "other",
            title: itemType,
            text: null,
            callId: itemId,
            status: "unknown",
            details: { type: "other", summary: itemType },
          }),
        );
        continue;
      }
      if (eventType === "task_started" || eventType === "task_complete" || eventType === "turn_aborted") {
        const event =
          eventType === "task_started" ? "started" : eventType === "task_complete" ? "completed" : "aborted";
        const error = asString(asRecord(payload?.error)?.message) ?? asString(payload?.error);
        items.push(
          makeItem({
            agent: input.agent,
            record,
            kind: "turn",
            title: `turn ${event}`,
            text: error,
            callId: null,
            status: event === "aborted" ? "aborted" : error ? "error" : "ok",
            details: { type: "turn", event, error },
          }),
        );
        continue;
      }
      if (eventType === "thread_settings_applied") {
        items.push(
          makeItem({
            agent: input.agent,
            record,
            kind: "other",
            title: "thread settings applied",
            text: null,
            callId: null,
            status: "ok",
            details: { type: "other", summary: "thread settings applied" },
          }),
        );
        continue;
      }
      continue;
    }
    if (record.type === "token_usage_record") {
      const info = asRecord(payload?.info);
      const usage = asRecord(info?.last_token_usage) ?? asRecord(info?.total_token_usage) ?? {};
      const inputTokens = asNumber(usage.input_tokens) ?? 0;
      const outputTokens = asNumber(usage.output_tokens) ?? 0;
      const totalTokens = asNumber(usage.total_tokens) ?? inputTokens + outputTokens;
      const cachedInputTokens = asNumber(usage.cached_input_tokens);
      items.push(
        makeItem({
          agent: input.agent,
          record,
          kind: "token-usage",
          title: "token usage",
          text: `input ${inputTokens} · output ${outputTokens} · total ${totalTokens}`,
          callId: null,
          status: "ok",
          details: { type: "token-usage", inputTokens, outputTokens, totalTokens, cachedInputTokens },
        }),
      );
      continue;
    }
    if (record.type === "compacted") {
      const summary = asString(payload?.message) ?? asString(payload?.retained_context);
      items.push(
        makeItem({
          agent: input.agent,
          record,
          kind: "context-compaction",
          title: "context compaction",
          text: summary,
          callId: null,
          status: "ok",
          details: { type: "context-compaction", summary },
        }),
      );
      continue;
    }
    items.push(
      makeItem({
        agent: input.agent,
        record,
        kind: "other",
        title: record.type,
        text: null,
        callId: null,
        status: "unknown",
        details: { type: "other", summary: record.type },
      }),
    );
  }
  return items;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm --filter @harness/web typecheck && pnpm --filter @harness/web exec vitest run src/prototype/snapshot/timeline.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/prototype/snapshot/timeline.ts apps/web/src/prototype/snapshot/timeline.test.ts
git commit -m "feat: 归一化 rollout 时间线并去除重复事件 (#10)"
```

---

## Task 6: Lazy rollout loading and explicit measurement

**Files:**
- Create: `apps/web/src/prototype/snapshot/load.ts`
- Create: `apps/web/src/prototype/snapshot/measure.ts`
- Create: `apps/web/src/prototype/snapshot/load.test.ts`
- Create: `apps/web/src/prototype/snapshot/measure.test.ts`

**Interfaces:**
- Consumes: `SessionFamily`, `AgentStats`; `buildFamilyIndex`, `toTimelineItems`, `countAgentStats`.
- Produces: `inferAgentStatus(records): AgentStatus`, `loadRollout(input): Promise<LoadedRollout>`, `countAgentStats(agent, records): AgentStats`, `measureFamily(input: { family; source }): Promise<SessionFamily>`.

- [ ] **Step 1: Write the failing load and measure tests**

```ts
// apps/web/src/prototype/snapshot/load.test.ts
import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { eventLine, metaLine, responseLine } from "./fixtures";
import { loadRollout } from "./load";
import { createMemorySnapshotSource } from "./memory-source";

function source() {
  return createMemorySnapshotSource({
    "root.jsonl": [
      metaLine({ threadId: "r" }),
      responseLine(1, { type: "message", role: "user", content: [{ type: "input_text", text: "root" }] }),
      eventLine(2, { type: "task_complete", turn_id: "t1" }),
    ],
    "root-cont.jsonl": [
      metaLine({ threadId: "r", timestamp: "2026-10-18T01:00:00.000Z" }),
      responseLine(3, { type: "message", role: "user", content: [{ type: "input_text", text: "continued" }] }),
    ],
    "a.jsonl": [
      metaLine({ threadId: "a", parentThreadId: "r", depth: 1, agentPath: "/root/a" }),
      responseLine(1, { type: "message", role: "user", content: [{ type: "input_text", text: "child" }] }),
      eventLine(2, { type: "task_complete", turn_id: "t2" }),
    ],
  });
}

describe("loadRollout", () => {
  it("reads only the requested agent and infers status from turns", async () => {
    const memory = source();
    const index = await buildFamilyIndex({ roots: ["r"], source: memory });
    const family = index.families[0];
    if (!family) throw new Error("family missing");

    const loaded = await loadRollout({ threadId: "a", family, source: memory });

    expect(memory.calls.recordsRolloutIds).toEqual(["a.jsonl"]);
    expect(loaded.records).toHaveLength(3);
    expect(loaded.timeline.map((item) => item.kind)).toEqual(["user-message", "turn"]);
    expect(loaded.status).toBe("completed");
    expect(loaded.stats.recordCount).toBe(3);
  });

  it("loads continuation segments only when requested", async () => {
    const memory = source();
    const index = await buildFamilyIndex({ roots: ["r"], source: memory });
    const family = index.families[0];
    if (!family) throw new Error("family missing");

    await loadRollout({ threadId: "r", family, source: memory });
    expect(memory.calls.recordsRolloutIds).toEqual(["root.jsonl"]);

    memory.calls.recordsRolloutIds.length = 0;
    await loadRollout({ threadId: "r", family, source: memory, includeContinuation: true });
    expect(memory.calls.recordsRolloutIds.sort()).toEqual(["root-cont.jsonl", "root.jsonl"]);
  });
});
```

```ts
// apps/web/src/prototype/snapshot/measure.test.ts
import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { eventLine, metaLine, responseLine } from "./fixtures";
import { measureFamily } from "./measure";
import { createMemorySnapshotSource } from "./memory-source";

describe("measureFamily", () => {
  it("counts primary and continuation records separately", async () => {
    const source = createMemorySnapshotSource({
      "root.jsonl": [
        metaLine({ threadId: "r" }),
        responseLine(1, { type: "message", role: "user", content: [] }),
        eventLine(2, { type: "task_complete", turn_id: "t1" }),
      ],
      "root-cont.jsonl": [
        metaLine({ threadId: "r", timestamp: "2026-10-18T01:00:00.000Z" }),
      ],
      "a.jsonl": [
        metaLine({ threadId: "a", parentThreadId: "r", depth: 1, agentPath: "/root/a" }),
        responseLine(1, { type: "message", role: "user", content: [] }),
      ],
    });
    const index = await buildFamilyIndex({ roots: ["r"], source });
    const family = index.families[0];
    if (!family) throw new Error("family missing");

    const measured = await measureFamily({ family, source });

    expect(measured.stats.recordCount).toBe(5);
    expect(measured.stats.continuationRecordCount).toBe(1);
    expect(measured.stats.rolloutCount).toBe(2);
    expect(measured.stats.segmentCount).toBe(3);
    expect(measured.stats.maxDepth).toBe(1);
    expect(measured.agents.find((agent) => agent.threadId === "a")?.stats.recordCount).toBe(2);
    expect(source.calls.recordsRolloutIds.sort()).toEqual([
      "a.jsonl",
      "root-cont.jsonl",
      "root.jsonl",
    ]);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm --filter @harness/web exec vitest run src/prototype/snapshot/load.test.ts src/prototype/snapshot/measure.test.ts`
Expected: FAIL because `./load` and `./measure` do not exist.

- [ ] **Step 3: Implement measurement and loading**

Create `apps/web/src/prototype/snapshot/measure.ts`:

```ts
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
```

Create `apps/web/src/prototype/snapshot/load.ts`:

```ts
import type { AgentStatus, SessionFamily } from "@harness/contracts";
import type { LoadedRollout, RolloutRecord, SnapshotSource } from "./types";
import { asRecord, asString } from "./payload";
import { countAgentStats } from "./measure";
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
    if (eventType === "turn_aborted") aborted = true;
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
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm --filter @harness/web typecheck && pnpm --filter @harness/web exec vitest run src/prototype/snapshot/load.test.ts src/prototype/snapshot/measure.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/prototype/snapshot/load.ts apps/web/src/prototype/snapshot/measure.ts apps/web/src/prototype/snapshot/load.test.ts apps/web/src/prototype/snapshot/measure.test.ts
git commit -m "feat: 按需加载 rollout 并测量家族统计 (#10)"
```

---

## Task 7: Four cross-agent example findings and evidence resolution

**Files:**
- Create: `apps/web/src/prototype/snapshot/findings.fixture.ts`
- Modify: `apps/web/src/prototype/snapshot/evidence.ts`
- Create: `apps/web/src/prototype/snapshot/findings.test.ts`

**Interfaces:**
- Consumes: `Finding`, `EvidenceRef`, `SessionFamily`, `AttributionTarget`; `SnapshotSource`, `evidenceForRecord`.
- Produces: `EXAMPLE_FINDINGS: readonly Finding[]`, `resolveFinding(input: { finding; family; source }): Promise<ResolvedFinding>`.

- [ ] **Step 1: Write the failing findings tests**

```ts
// apps/web/src/prototype/snapshot/findings.test.ts
import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { evidenceForRecord, resolveFinding } from "./evidence";
import { EXAMPLE_FINDINGS } from "./findings.fixture";
import { metaLine, responseLine } from "./fixtures";
import { createMemorySnapshotSource } from "./memory-source";
import { toRecord } from "./meta";

describe("example findings", () => {
  it("contains at least three cross-agent findings with stable anchors", () => {
    expect(EXAMPLE_FINDINGS.length).toBeGreaterThanOrEqual(3);
    for (const finding of EXAMPLE_FINDINGS) {
      expect(new Set(finding.sourceAgentThreadIds).size).toBeGreaterThanOrEqual(2);
      expect(finding.attribution.target.id).toMatch(/^(skill|agent):/);
      expect(finding.evidence.length).toBeGreaterThanOrEqual(2);
      for (const anchor of finding.evidence) {
        expect(anchor.id).toBe(`${anchor.rolloutId}#${anchor.ordinal}`);
      }
    }
  });

  it("resolves an evidence ordinal back to its current line and call id", async () => {
    const source = createMemorySnapshotSource({
      "root.jsonl": [metaLine({ threadId: "r" })],
      "a.jsonl": [
        metaLine({ threadId: "a", parentThreadId: "r", depth: 1, agentPath: "/root/a", nickname: "A" }),
        responseLine(1, {
          type: "function_call",
          call_id: "call-1",
          name: "exec_command",
          arguments: JSON.stringify({ cmd: "cat skills/foo/SKILL.md" }),
        }),
      ],
    });
    const index = await buildFamilyIndex({ roots: ["r"], source });
    const family = index.families[0];
    if (!family) throw new Error("family missing");
    const agent = family.agents.find((candidate) => candidate.threadId === "a");
    if (!agent) throw new Error("agent missing");
    const record = toRecord(
      "a.jsonl",
      responseLine(1, {
        type: "function_call",
        call_id: "call-1",
        name: "exec_command",
        arguments: JSON.stringify({ cmd: "cat skills/foo/SKILL.md" }),
      }),
      2,
    );
    if (!record) throw new Error("record missing");
    const anchor = evidenceForRecord(agent, record, { excerpt: "skills/foo/SKILL.md" });
    const finding = {
      ...EXAMPLE_FINDINGS[0]!,
      familyRootThreadId: "r",
      sourceAgentThreadIds: ["a"],
      attribution: {
        ...EXAMPLE_FINDINGS[0]!.attribution,
        target: { type: "agent", id: "agent:a", name: "A" },
      },
      evidence: [anchor],
    };

    const resolved = await resolveFinding({ finding, family, source });

    expect(resolved.target.type).toBe(finding.attribution.target.type);
    expect(resolved.evidence[0]).toMatchObject({
      rolloutId: "a.jsonl",
      ordinal: 1,
      line: 2,
      callId: "call-1",
      agentThreadId: "a",
    });
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pnpm --filter @harness/web exec vitest run src/prototype/snapshot/findings.test.ts`
Expected: FAIL because `./findings.fixture` and `resolveFinding` do not exist.

- [ ] **Step 3: Add the fixture and resolver**

Create `apps/web/src/prototype/snapshot/findings.fixture.ts`:

```ts
import type { EvidenceRef, Finding } from "@harness/contracts";

function anchor(input: {
  agentThreadId: string;
  agentPath: string;
  rolloutId: string;
  ordinal: number;
  line: number;
  callId: string | null;
  turnId: string | null;
  excerpt: string;
}): EvidenceRef {
  return {
    id: `${input.rolloutId}#${input.ordinal}`,
    rolloutId: input.rolloutId,
    agentThreadId: input.agentThreadId,
    agentPath: input.agentPath,
    ordinal: input.ordinal,
    line: input.line,
    recordType: "response_item",
    turnId: input.turnId,
    callId: input.callId,
    itemId: null,
    excerpt: input.excerpt,
  };
}

/**
 * Hand-curated cross-agent findings derived from the four M1 session families.
 * The fixture contains identifiers and short excerpts, never raw JSONL.
 */
export const EXAMPLE_FINDINGS: readonly Finding[] = [
  {
    id: "finding:gh-network-duplication",
    familyRootThreadId: "01a14ee6-d117-7c71-84a7-32b46bb3a99b",
    title: "多个子 agent 重复执行 gh 查询，网络不可达时未短路",
    summary:
      "主 agent 并行派发 review 子任务后，多个子 agent 各自执行 gh pr view，均因 api.github.com 不可达失败；没有先集中探测网络或共享 PR 元数据。",
    impact: "子 agent 在启动阶段浪费轮次，证据收集被同一基础设施故障阻塞。",
    severity: "P1",
    category: "agent-orchestration",
    sourceAgentThreadIds: [
      "01a14ee6-d117-7c71-84a7-32b46bb3a99b",
      "01a14f27-84f3-73f2-a259-7525d73bbdff",
      "01a14f27-b7f1-7391-b6fd-f38afb01ced5",
      "01a14f28-0adb-7b31-b8fe-ff99dd8dabb0",
      "01a14f2b-bdaa-7582-9710-a14af43f8016",
      "01a14f2f-4288-7452-ae4d-93d570c13801",
      "01a14f43-0227-7811-aa2b-ab6efe3e146d",
    ],
    attribution: {
      target: {
        type: "agent",
        id: "agent:01a14ee6-d117-7c71-84a7-32b46bb3a99b",
        name: "root",
      },
      reason: "根 agent 负责派发与共享上下文，未在派发前验证 GitHub 可达性，也未缓存 PR 元数据。",
      confidence: "confirmed",
      unverified: "未验证是否存在可用的离线 PR 元数据缓存。",
    },
    evidence: [
      anchor({
        agentThreadId: "01a14ee6-d117-7c71-84a7-32b46bb3a99b",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T20-05-12-01a14ee6-d117-7c71-84a7-32b46bb3a99b.jsonl",
        ordinal: 25,
        line: 26,
        callId: "call_02_RR3gdCv9Z23GipOosQkQ0942",
        turnId: "01a14ee6-d4b9-71d1-9dd3-af81c724edd4",
        excerpt: "Process exited with code 1; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f27-84f3-73f2-a259-7525d73bbdff",
        agentPath: "/root/v64_dependency_semantics",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-15-52-01a14f27-84f3-73f2-a259-7525d73bbdff.jsonl",
        ordinal: 70,
        line: 71,
        callId: "call_01_uE9THjcJtyIpTHlZwYi89204",
        turnId: "01a14f27-855b-78d2-b7cb-2ae5997a0d60",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f27-b7f1-7391-b6fd-f38afb01ced5",
        agentPath: "/root/v64_dependency_semantics/analyze_64_inject_semantics",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-16-05-01a14f27-b7f1-7391-b6fd-f38afb01ced5.jsonl",
        ordinal: 79,
        line: 80,
        callId: "call_01_kNk1cNocLJyVn0tYAkkP4862",
        turnId: "01a14f27-b84e-7843-a2d8-5a2ca558cd16",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f28-0adb-7b31-b8fe-ff99dd8dabb0",
        agentPath: "/root/v64_dependency_semantics/analyze_64_inject_semantics/analyze_6_4",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-16-26-01a14f28-0adb-7b31-b8fe-ff99dd8dabb0.jsonl",
        ordinal: 78,
        line: 79,
        callId: "call_03_bt0whwYZhOh95u8dKWWT0571",
        turnId: "01a14f28-0b28-7631-9294-da443573a418",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f2b-bdaa-7582-9710-a14af43f8016",
        agentPath: "/root/v64_dependency_semantics/fix_64_inject_semantics",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-20-29-01a14f2b-bdaa-7582-9710-a14af43f8016.jsonl",
        ordinal: 80,
        line: 81,
        callId: "call_01_tdk3BPVAcHynM1CoTYiH0441",
        turnId: "01a14f2b-be01-76e1-9c87-5b3ec167712e",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f2f-4288-7452-ae4d-93d570c13801",
        agentPath:
          "/root/v64_dependency_semantics/fix_64_inject_semantics/fix_64_contract_wording",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-24-19-01a14f2f-4288-7452-ae4d-93d570c13801.jsonl",
        ordinal: 78,
        line: 79,
        callId: "call_02_ArRAT7LvNooyyhZxJfOC7017",
        turnId: "01a14f2f-42d8-7dc3-849a-954c5ef86d7b",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
      anchor({
        agentThreadId: "01a14f43-0227-7811-aa2b-ab6efe3e146d",
        agentPath: "/root/v64_review_with_context",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T21-45-54-01a14f43-0227-7811-aa2b-ab6efe3e146d.jsonl",
        ordinal: 71,
        line: 72,
        callId: "call_02_XYSCb47a9L53KhexqKQH9216",
        turnId: "01a14f43-02e6-71a3-b02a-11700fa5db08",
        excerpt: "gh pr view 62; error connecting to api.github.com",
      }),
    ],
    status: "example",
  },
  {
    id: "finding:skill-path-drift",
    familyRootThreadId: "01a14e5b-5d48-7382-9fed-1d2295a163c1",
    title: "同一 skill 通过三种缓存路径加载",
    summary:
      "根 agent 与 4 个子 agent 都读取 systematic-debugging，但路径分别落在 claude-plugins cache、.tmp/plugins 与 openai-api-curated cache。",
    impact: "按路径统计会把同一 skill 拆成多个目标，归因与自进化聚合会断裂。",
    severity: "P1",
    category: "skill-usage",
    sourceAgentThreadIds: [
      "01a14e5b-5d48-7382-9fed-1d2295a163c1",
      "01a14e89-414a-7bb3-80bb-20c8eaa8a434",
      "01a14e91-3dbe-7840-98d0-a24878372cf6",
      "01a14e92-3207-7ed0-ab92-226edf2d4bf4",
      "01a14e92-33a1-74a1-8366-9fbe66c1aee3",
    ],
    attribution: {
      target: {
        type: "skill",
        id: "skill:systematic-debugging",
        name: "systematic-debugging",
      },
      reason: "5 个 agent 的显式 SKILL.md 读取都指向同一 basename，差异只在缓存根。",
      confidence: "confirmed",
      unverified: null,
    },
    evidence: [
      anchor({
        agentThreadId: "01a14e5b-5d48-7382-9fed-1d2295a163c1",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T17-32-52-01a14e5b-5d48-7382-9fed-1d2295a163c1.jsonl",
        ordinal: 1131,
        line: 1132,
        callId: "call_00_kLCFOMMftAqnOORf2c3J7472",
        turnId: "01a14e83-4785-7053-b0e0-0715541f0db2",
        excerpt: ".../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14e89-414a-7bb3-80bb-20c8eaa8a434",
        agentPath: "/root/debug_nested_sources2",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T18-23-00-01a14e89-414a-7bb3-80bb-20c8eaa8a434.jsonl",
        ordinal: 62,
        line: 63,
        callId: "call_00_uNhhDyI8MTVY0nHc1n2p7569",
        turnId: "01a14e89-421d-7803-bb7d-46a065876f78",
        excerpt: ".../.tmp/plugins/plugins/superpowers/skills/systematic-debugging/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14e91-3dbe-7840-98d0-a24878372cf6",
        agentPath: "/root/review_pr62_fixes",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T18-31-43-01a14e91-3dbe-7840-98d0-a24878372cf6.jsonl",
        ordinal: 63,
        line: 64,
        callId: "call_00_hx58WmK0KfuMDvTuAfCV4524",
        turnId: "01a14e91-3e0e-74f0-8a5f-096cb7cbcb13",
        excerpt: ".../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14e92-3207-7ed0-ab92-226edf2d4bf4",
        agentPath: "/root/explain_arch_flow2",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T18-32-46-01a14e92-3207-7ed0-ab92-226edf2d4bf4.jsonl",
        ordinal: 100,
        line: 101,
        callId: "call_00_fpQl4sx1Tc87VkIMUmkT1185",
        turnId: "01a14e92-3262-7891-acab-64faf3a4476d",
        excerpt: ".../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14e92-33a1-74a1-8366-9fbe66c1aee3",
        agentPath: "/root/explain_design_flow2",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T18-32-46-01a14e92-33a1-74a1-8366-9fbe66c1aee3.jsonl",
        ordinal: 49,
        line: 50,
        callId: "call_00_oRi853rCVqQHXo9Jexvs2853",
        turnId: "01a14e92-33f4-73b2-82c5-ad1f5de9bc83",
        excerpt: ".../openai-api-curated/superpowers/0722921d/skills/systematic-debugging/SKILL.md",
      }),
    ],
    status: "example",
  },
  {
    id: "finding:walkthrough-skill-reload",
    familyRootThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
    title: "walkthrough skill 被根 agent 反复加载 31 次",
    summary:
      "根 agent 在同一 turn 内多次读取 walkthrough-change-metadata-gen/SKILL.md，首次还因路径错误失败；子 agent Copernicus 又独立加载一次。",
    impact: "重复读取挤占上下文与轮次，且暴露 skill 路径与缓存策略不一致。",
    severity: "P1",
    category: "skill-usage",
    sourceAgentThreadIds: [
      "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
      "01a14d0b-a483-7443-aa78-1fd24e70f1b2",
    ],
    attribution: {
      target: {
        type: "skill",
        id: "skill:walkthrough-change-metadata-gen",
        name: "walkthrough-change-metadata-gen",
      },
      reason: "显式读取证据集中在根 agent，子 agent 未复用同一 skill 上下文。",
      confidence: "confirmed",
      unverified: "31 次计数来自 SKILL.md 调用匹配，未区分读取片段大小。",
    },
    evidence: [
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 14,
        line: 15,
        callId: "exec_command_2_96bf433e",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "cat ~/.agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 19,
        line: 20,
        callId: "exec_command_2_96bf433e",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "Process exited with code 1; cat: .../SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 52,
        line: 53,
        callId: "exec_command_10_98bc8746",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "cat .agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 70,
        line: 71,
        callId: "exec_command_14_e499f71a",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "cat .agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T08-46-41-01a14c79-9e02-7210-ada9-ae4ff5c6ae05.jsonl",
        ordinal: 79,
        line: 80,
        callId: "exec_command_16_04d76d52",
        turnId: "01a14c7a-2b62-78e2-b2c3-9c4cf582b8c0",
        excerpt: "cat .agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14d0b-a483-7443-aa78-1fd24e70f1b2",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T11-26-11-01a14d0b-a483-7443-aa78-1fd24e70f1b2.jsonl",
        ordinal: 10,
        line: 11,
        callId: "call_118a1f53b8364a49a71440a6",
        turnId: "01a14d0b-a58e-7ee0-a2b2-38c31d85beec",
        excerpt: "sed -n '1,240p' .agents/skills/walkthrough-change-metadata-gen/SKILL.md",
      }),
    ],
    status: "example",
  },
  {
    id: "finding:parallel-patch-conflict",
    familyRootThreadId: "01a14d49-f4a0-7c31-ad9a-b6e3c034501a",
    title: "并行子 agent 在共享文件上反复 patch 失败",
    summary:
      "根 agent 使用 subagent-driven-development 并行派发任务，多个子 agent 对同一批文件执行 apply_patch，出现 expected lines 找不到与上下文失效。",
    impact: "子 agent 反复重试同一 patch，主 agent 需要额外轮次收敛，验证证据被稀释。",
    severity: "P1",
    category: "agent-orchestration",
    sourceAgentThreadIds: [
      "01a14d49-f4a0-7c31-ad9a-b6e3c034501a",
      "01a14da6-7e05-7c33-b31d-24e1c536a0b1",
      "01a14db0-def4-7f11-b141-3b975cfa1966",
      "01a14dd4-d983-79a2-989a-9020266b6b50",
      "01a14de9-8a81-7ab3-a39f-40cddf00c34f",
    ],
    attribution: {
      target: {
        type: "skill",
        id: "skill:subagent-driven-development",
        name: "subagent-driven-development",
      },
      reason: "并行工作流由该 skill 指导，但没有按文件分区或串行化共享文件写入。",
      confidence: "inferred",
      unverified: "未验证每个 patch 失败是否都源于同一文件的并发写入。",
    },
    evidence: [
      anchor({
        agentThreadId: "01a14d49-f4a0-7c31-ad9a-b6e3c034501a",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T12-34-14-01a14d49-f4a0-7c31-ad9a-b6e3c034501a.jsonl",
        ordinal: 586,
        line: 587,
        callId: "call_adcd2b1d64a94184b26b6c25",
        turnId: "01a14d92-92b9-7922-9d6b-cd0695c86952",
        excerpt: ".../claude-plugins-official/superpowers/6.4.1/skills/subagent-driven-development/SKILL.md",
      }),
      anchor({
        agentThreadId: "01a14da6-7e05-7c33-b31d-24e1c536a0b1",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T14-15-19-01a14da6-7e05-7c33-b31d-24e1c536a0b1.jsonl",
        ordinal: 154,
        line: 155,
        callId: "call_d72feafbe6e84c3cb2646636",
        turnId: "01a14da6-7e8b-7480-b419-0de0ca9a831f",
        excerpt: "apply_patch verification failed: Failed to find expected lines",
      }),
      anchor({
        agentThreadId: "01a14db0-def4-7f11-b141-3b975cfa1966",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T14-26-39-01a14db0-def4-7f11-b141-3b975cfa1966.jsonl",
        ordinal: 208,
        line: 209,
        callId: "call_ac6fd8dbc41f4e299388529c",
        turnId: "01a14db0-df74-7ca0-9001-96ad351cc28e",
        excerpt: "Process exited with code 1; Failed to find expected lines",
      }),
      anchor({
        agentThreadId: "01a14dd4-d983-79a2-989a-9020266b6b50",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T15-05-57-01a14dd4-d983-79a2-989a-9020266b6b50.jsonl",
        ordinal: 264,
        line: 265,
        callId: "call_1e777787e4bc4dd9b9f0c523",
        turnId: "01a14dd4-d9de-7700-867b-17b1ab13f7e8",
        excerpt: "Process exited with code 1; Failed to find expected lines",
      }),
      anchor({
        agentThreadId: "01a14de9-8a81-7ab3-a39f-40cddf00c34f",
        agentPath: "/",
        rolloutId:
          "2026/10/18/rollout-2026-10-18T15-28-33-01a14de9-8a81-7ab3-a39f-40cddf00c34f.jsonl",
        ordinal: 386,
        line: 387,
        callId: "call_f9b31f29185a404d886be322",
        turnId: "01a14de9-8af7-79d1-89e9-cd2884421806",
        excerpt: "apply_patch verification failed: Failed to find expected lines",
      }),
    ],
    status: "example",
  },
];
```

Replace `apps/web/src/prototype/snapshot/evidence.ts` with:

```ts
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pnpm --filter @harness/web typecheck && pnpm --filter @harness/web exec vitest run src/prototype/snapshot/findings.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/prototype/snapshot/findings.fixture.ts apps/web/src/prototype/snapshot/evidence.ts apps/web/src/prototype/snapshot/findings.test.ts
git commit -m "feat: 加入跨 agent 示例问题与证据解析 (#10)"
```

---

## Task 8: Node filesystem source and local acceptance test

**Files:**
- Modify: `apps/web/package.json` (add `@types/node` dev dependency)
- Modify: `apps/web/tsconfig.json` (add `"node"` to `types`)
- Modify: `pnpm-lock.yaml` (generated by pnpm)
- Create: `apps/web/src/prototype/snapshot/node-source.ts`
- Create: `apps/web/src/prototype/snapshot/node-source.test.ts`
- Create: `apps/web/src/prototype/snapshot/local-snapshot.test.ts`

**Interfaces:**
- Consumes: `SnapshotSource`, `parseSessionMeta`, `toRecord`, `buildFamilyIndex`, `measureFamily`, `EXAMPLE_FINDINGS`, `resolveFinding`.
- Produces: `createNodeSnapshotSource(sessionsRoot: string): SnapshotSource`.

- [ ] **Step 1: Add Node typings**

Run: `pnpm add -D @types/node@24.19.2 --filter @harness/web`

Modify `apps/web/tsconfig.json`:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "jsx": "react-jsx",
    "noEmit": true,
    "types": ["vite/client", "node"]
  },
  "include": ["src"]
}
```

- [ ] **Step 2: Write the failing Node source and local acceptance tests**

```ts
// apps/web/src/prototype/snapshot/node-source.test.ts
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { metaLine, responseLine } from "./fixtures";
import { createNodeSnapshotSource } from "./node-source";

let tempRoot: string | null = null;

afterEach(async () => {
  if (tempRoot) {
    await rm(tempRoot, { recursive: true, force: true });
    tempRoot = null;
  }
});

describe("createNodeSnapshotSource", () => {
  it("lists nested rollouts and reads only the requested file", async () => {
    tempRoot = await mkdtemp(path.join(tmpdir(), "harness-snapshot-"));
    await mkdir(path.join(tempRoot, "2026/10/18"), { recursive: true });
    await writeFile(
      path.join(tempRoot, "2026/10/18/root.jsonl"),
      `${metaLine({ threadId: "r" })}\n${responseLine(1, { type: "message", role: "user", content: [] })}\n`,
      "utf8",
    );
    await writeFile(
      path.join(tempRoot, "2026/10/18/a.jsonl"),
      `${metaLine({ threadId: "a", parentThreadId: "r", depth: 1, agentPath: "/root/a" })}\n`,
      "utf8",
    );

    const source = createNodeSnapshotSource(tempRoot);
    const files = await source.listRollouts();
    const meta = await source.readMeta("2026/10/18/a.jsonl");
    const records = await source.readRecords("2026/10/18/root.jsonl");

    expect(files.map((file) => file.rolloutId)).toEqual([
      "2026/10/18/a.jsonl",
      "2026/10/18/root.jsonl",
    ]);
    expect(meta.threadId).toBe("a");
    expect(records.map((record) => record.ordinal)).toEqual([0, 1]);
  });
});
```

```ts
// apps/web/src/prototype/snapshot/local-snapshot.test.ts
import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { EXAMPLE_FINDINGS } from "./findings.fixture";
import { measureFamily } from "./measure";
import { createNodeSnapshotSource } from "./node-source";
import { resolveFinding } from "./evidence";

const localRoot = process.env.HARNESS_SNAPSHOT_ROOT;
const roots = [
  "01a14ee6-d117-7c71-84a7-32b46bb3a99b",
  "01a14e5b-5d48-7382-9fed-1d2295a163c1",
  "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
  "01a14d49-f4a0-7c31-ad9a-b6e3c034501a",
];

describe.skipIf(!localRoot)("local four-family acceptance", () => {
  it("reproduces the 64/25,170/72.2MB/depth-4 baseline without eager record reads", async () => {
    const base = createNodeSnapshotSource(localRoot!);
    let recordReads = 0;
    const source = {
      listRollouts: () => base.listRollouts(),
      readMeta: (rolloutId: string) => base.readMeta(rolloutId),
      readRecords: async (rolloutId: string) => {
        recordReads += 1;
        return base.readRecords(rolloutId);
      },
    };

    const index = await buildFamilyIndex({ roots, source, findings: EXAMPLE_FINDINGS });
    expect(index.families).toHaveLength(4);
    expect(recordReads).toBe(0);

    const measured = await Promise.all(
      index.families.map((family) => measureFamily({ family, source })),
    );
    expect(measured.reduce((sum, family) => sum + family.stats.rolloutCount, 0)).toBe(64);
    expect(measured.reduce((sum, family) => sum + (family.stats.recordCount ?? 0), 0)).toBe(25170);
    expect(
      measured.reduce((sum, family) => sum + (family.stats.continuationRecordCount ?? 0), 0),
    ).toBe(12);
    expect(measured.reduce((sum, family) => sum + family.stats.byteCount, 0)).toBeGreaterThan(
      75_000_000,
    );
    expect(measured.reduce((max, family) => Math.max(max, family.stats.maxDepth), 0)).toBe(4);

    for (const family of measured) {
      for (const finding of family.findings) {
        const resolved = await resolveFinding({ finding, family, source });
        expect(resolved.evidence.length).toBeGreaterThanOrEqual(2);
      }
    }
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pnpm --filter @harness/web typecheck`
Expected: FAIL because `./node-source` does not exist.

- [ ] **Step 4: Implement the Node source**

Create `apps/web/src/prototype/snapshot/node-source.ts`:

```ts
import { createReadStream } from "node:fs";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import readline from "node:readline";
import { parseSessionMeta, toRecord } from "./meta";
import type {
  RolloutFileRef,
  RolloutRecord,
  RolloutSessionMeta,
  SnapshotSource,
} from "./types";

async function collectJsonl(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await collectJsonl(full)));
    else if (entry.isFile() && entry.name.endsWith(".jsonl")) files.push(full);
  }
  return files;
}

async function firstLine(file: string): Promise<string> {
  const stream = createReadStream(file, { encoding: "utf8" });
  const lines = readline.createInterface({ input: stream, crlfDelay: Infinity });
  try {
    for await (const line of lines) return line;
    return "";
  } finally {
    lines.close();
    stream.destroy();
  }
}

/**
 * Create a Node filesystem snapshot source.
 * @param sessionsRoot Directory containing Codex rollout JSONL files.
 * @returns Snapshot source rooted at the directory.
 */
export function createNodeSnapshotSource(sessionsRoot: string): SnapshotSource {
  const root = path.resolve(sessionsRoot);
  const resolveFile = (rolloutId: string): string => {
    const file = path.resolve(root, rolloutId);
    if (file !== root && !file.startsWith(`${root}${path.sep}`)) {
      throw new Error(`rolloutId escapes sessions root: ${rolloutId}`);
    }
    return file;
  };
  return {
    async listRollouts(): Promise<readonly RolloutFileRef[]> {
      const files = await collectJsonl(root);
      const refs = await Promise.all(
        files.map(async (file) => {
          const info = await stat(file);
          return {
            rolloutId: path.relative(root, file).split(path.sep).join("/"),
            byteCount: info.size,
            modifiedAt: info.mtime.toISOString(),
          };
        }),
      );
      return refs.sort((left, right) => left.rolloutId.localeCompare(right.rolloutId));
    },
    async readMeta(rolloutId: string): Promise<RolloutSessionMeta> {
      const line = await firstLine(resolveFile(rolloutId));
      const meta = parseSessionMeta(line, rolloutId);
      if (!meta) throw new Error(`invalid session_meta: ${rolloutId}`);
      return meta;
    },
    async readRecords(rolloutId: string): Promise<readonly RolloutRecord[]> {
      const text = await readFile(resolveFile(rolloutId), "utf8");
      return text
        .split("\n")
        .map((line, index) => (line.length > 0 ? toRecord(rolloutId, line, index + 1) : null))
        .filter((record): record is RolloutRecord => record !== null);
    },
  };
}
```

- [ ] **Step 5: Run the tests**

Run: `pnpm --filter @harness/web typecheck && pnpm --filter @harness/web exec vitest run src/prototype/snapshot/node-source.test.ts`
Expected: PASS.

Run the local acceptance test with the real snapshot root:

```bash
HARNESS_SNAPSHOT_ROOT="$HOME/.codex/sessions" pnpm --filter @harness/web exec vitest run src/prototype/snapshot/local-snapshot.test.ts
```

Expected: PASS with 4 families, 64 rollouts, 25,170 primary records, 12 continuation records, and max depth 4.

- [ ] **Step 6: Commit**

```bash
git add apps/web/package.json apps/web/tsconfig.json pnpm-lock.yaml apps/web/src/prototype/snapshot/node-source.ts apps/web/src/prototype/snapshot/node-source.test.ts apps/web/src/prototype/snapshot/local-snapshot.test.ts
git commit -m "feat: 接入本地 rollout 文件源并验证四家族基线 (#10)"
```

---

## Task 9: Flow, Agent Note, and full verification

**Files:**
- Modify: `.agents/flow/issues/m1-contracts-snapshot-loader.md`
- Modify: `.agents/flow/issues/m1-contracts-snapshot-loader.en.md`
- Modify: `.agents/notes/proposed/architecture/2026-10-19-session-family-prototype.md`
- Modify: `.agents/notes/proposed/architecture/2026-10-19-session-family-prototype.en.md`
- Generated: `.agents/flow/issues/m1-contracts-snapshot-loader.i18n.yaml`
- Generated: `.agents/notes/proposed/architecture/2026-10-19-session-family-prototype.i18n.yaml`

**Interfaces:**
- Consumes: all code tasks.
- Produces: a flow tree that permits the PR diff, an owning Agent Note that records the decision, and a fully verified branch.

- [ ] **Step 1: Expand the issue scope and mark it in progress**

Change the `yaml flow` block in both `.agents/flow/issues/m1-contracts-snapshot-loader.md` and `.en.md` to:

```yaml
kind: issue
milestone: m1
priority: P0
status: in-progress
scope:
  - packages/contracts/**
  - apps/web/src/prototype/**
  - apps/web/package.json
  - apps/web/tsconfig.json
  - scripts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - pnpm-lock.yaml
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 10
  url: https://github.com/Shadow-Azure/harness-evolution/issues/10
```

- [ ] **Step 2: Add the implementation decision to the owning Agent Note**

After the existing `## Decision` bullets in `.agents/notes/proposed/architecture/2026-10-19-session-family-prototype.md`, add:

```markdown
## M1 快照契约落地

- 索引层只读取每个 rollout 的首条 `session_meta`；正文按 thread 懒加载，原始 JSONL 不进入仓库。
- `threadId`（`payload.id`）是 agent 主键，`rolloutId`（相对路径）区分 segment，`sessionId` 只作展示字段。
- 同一 thread 的续段挂在同一 `AgentNode` 下；主段记录数与续段记录数分开报告。
- guardian review thread 不进入 Session Family；文件仍保留在原始目录，需要时可单独读取。
- 时间线以 `TimelineItem` 为稳定 envelope，保留 command、file-change、mcp、collab、subagent 与 token 等 item；`event_msg.item_completed` 与 `response_item` 按 id/call_id 去重。
- 浏览器读取路径不在 #10 范围；#14/#15 决定快照如何进入前端。
```

English counterpart:

```markdown
## M1 snapshot contract implementation

- The index reads only the first `session_meta` line of each rollout; bodies are loaded per thread on demand and raw JSONL never enters the repository.
- `threadId` (`payload.id`) is the agent key, `rolloutId` (relative path) distinguishes segments, and `sessionId` is display-only.
- Continuation segments share one `AgentNode` with the primary segment; primary and continuation record counts are reported separately.
- Guardian review threads stay outside the Session Family; their files remain in the original directory and can be read independently.
- `TimelineItem` is the stable envelope for commands, file changes, MCP calls, collaboration calls, subagent activity, and token usage; duplicate `event_msg.item_completed` and `response_item` entries are removed by id/call_id.
- Browser wiring is out of scope for #10; #14/#15 decide how the snapshot reaches the frontend.
```

- [ ] **Step 3: Re-record the bilingual pairs**

Run:

```bash
pnpm record:i18n -- .agents/flow/issues/m1-contracts-snapshot-loader.md
pnpm record:i18n -- .agents/notes/proposed/architecture/2026-10-19-session-family-prototype.md
```

Expected: both `.i18n.yaml` files are rewritten and the pairing gate reports success.

- [ ] **Step 4: Run the full verification suite**

Run:

```bash
pnpm typecheck
pnpm test
pnpm build
pnpm verify:flow
pnpm verify:docs
pnpm verify:flow -- --diff main
```

Expected: all commands PASS. The diff check is the same scope gate CI runs on the PR.

- [ ] **Step 5: Commit**

```bash
git add .agents/flow/issues/m1-contracts-snapshot-loader.md .agents/flow/issues/m1-contracts-snapshot-loader.en.md .agents/flow/issues/m1-contracts-snapshot-loader.i18n.yaml .agents/notes/proposed/architecture/2026-10-19-session-family-prototype.md .agents/notes/proposed/architecture/2026-10-19-session-family-prototype.en.md .agents/notes/proposed/architecture/2026-10-19-session-family-prototype.i18n.yaml
git commit -m "docs: 记录 Session Family 快照落地 (#10)"
```

---

## Self-Review Checklist

- [ ] Every spec section maps to a task: contracts (Task 1), metadata/source (Task 2), index (Task 3), skills (Task 4), timeline (Task 5), lazy load/measure (Task 6), findings/evidence (Task 7), Node/local acceptance (Task 8), flow/note/gates (Task 9).
- [ ] No task contains `TBD`, `TODO`, or “similar to Task N”.
- [ ] Every test step contains runnable Vitest or pnpm code.
- [ ] `threadId`, `rolloutId`, `sessionId`, `recordCount`, and `continuationRecordCount` have the same meaning in every task.
- [ ] The four findings use `agent:` / `skill:` targets and `rolloutId#ordinal` anchors.
- [ ] Raw JSONL is never added to git; only synthetic fixtures and derived excerpts are committed.

