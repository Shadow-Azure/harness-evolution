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
