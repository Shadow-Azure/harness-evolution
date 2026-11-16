# Agent Note: Session parent-child reconciliation and unresolved branches

Status: implemented

English | [中文](2026-11-16-session-relation-reconciliation.md)

## Problem

M9-01/M9-02 can now parse real metadata, tool results, and execution completion, but the session tree still exposes only a binary linked/unlinked relation. When the parent `Agent` tool_use and the child metadata `toolUseId` agree but the tool result is missing, a real export is misread as unlinked. When only weak `parentAgentId` evidence exists, a node is silently attached to the main Agent. When no parent tool identity exists, the node may survive temporarily but has no stable relation evidence for the API or UI. Attribution and later runs therefore cannot tell strong evidence, a missing-result downgrade, weak synthetic evidence, and a fully unresolved branch apart.

## Decision

- Compute the relation level only during tree assembly: `authoritative` requires the parent `Agent` tool_use, the matching tool result in the parent transcript, and the child metadata `toolUseId` to agree; a matching tool_use and metadata without a parent result is `derived`.
- Generate a `synthetic` relation from `parentAgentId`-only evidence and append a deterministic synthetic `agent` trigger to the parent node. When no usable parent identity exists, generate an `unresolved` relation, keep the node under the main Agent, and retain the `MISSING_PARENT_TOOL_USE_ID` / `UNKNOWN_PARENT_TOOL_USE_ID` / `AMBIGUOUS_PARENT_TOOL_USE_ID` diagnostics so the node never disappears from the tree.
- Store the confidence on the parent node's `agent_events.relation_confidence`, matching the column semantics in [06 §3.4](../../../../plans/fullstack-design/06-database-design.md). `ParsedEvent` gains one optional field; the parser itself does not decide parentage.
- Keep `derived` children attached in source order and preserve their own execution completion. The frontend shows a relation evidence label and the design-mandated "未返回最终报告" warning for `derived` or a missing final report.
- Bump `ClaudeCodeTraceParser.parser_version` from 2 to 3 so existing `claude-code` payloads are reassembled and receive relation evidence on the next sync or replay. Relation classification is an assembly-semantic change, and leaving the version alone would keep legacy sessions at NULL forever.
- The 03/05/06 DTOs, database columns, and frontend fields already exist; this Note adds only the writer and the visible labels, with no new tables or duplicate fields.

## Alternatives considered

- **Keep a binary linked/unlinked state**: it cannot express the real missing-result downgrade and gives the UI no stable evidence identity. Rejected.
- **Put confidence on the `agents` row**: 06 defines `relation_confidence` on trigger events, and one Agent can be explained by several triggers; a node column would create two sources of truth. Rejected.
- **Drop the node when the result is missing**: that silently loses children that a real export contains, violating "unresolved nodes remain visible". Rejected.
- **Let the frontend infer relations from `toolUseId`**: the browser cannot see the parent transcript's tool result, so its guess would diverge from the export and internal assembly. Relation classification belongs to one assembly layer. Rejected.
- **Leave `parser_version` unchanged and replay by hand**: legacy real sessions would never receive relation evidence, and acceptance would cover new imports only. Rejected.

## Consequences

- Existing `claude-code` payloads replay once after deployment, at the same cost as the M9-02 version bump.
- Weak and unresolved nodes add one synthetic event at the end of the parent trigger chain so they remain visible in the tree and UI; this is not a claim that the provider emitted that event.
- An `unresolved` node is still structurally attached to the main Agent, while its relation evidence says unresolved; callers must read `relationConfidence` rather than parent-link presence to judge strength.
- Frontend nodes gain relation labels and a completion warning; non-authoritative levels use state colors, and historical sessions with NULL relation show no label.
- Potential matching, guessing parents from start time, and hiding unresolved nodes remain out of this slice.
- Classification covers Agent-tool-triggered children; forked-skill, workflow-subagent, and in-process-teammate edges are not parent Agent tool calls and keep `relation_confidence` NULL, so NULL cannot distinguish "not replayed" from "never classified".
