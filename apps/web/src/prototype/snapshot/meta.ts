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
