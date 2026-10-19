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
