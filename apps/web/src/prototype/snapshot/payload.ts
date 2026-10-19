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
