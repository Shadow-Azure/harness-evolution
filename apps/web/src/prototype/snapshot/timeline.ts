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
      if (
        eventType === "task_started" ||
        eventType === "task_complete" ||
        eventType === "turn_aborted" ||
        eventType === "task_aborted"
      ) {
        const event =
          eventType === "task_started"
            ? "started"
            : eventType === "task_complete"
              ? "completed"
              : "aborted";
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
