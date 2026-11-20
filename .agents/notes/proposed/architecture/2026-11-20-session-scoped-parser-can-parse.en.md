# Agent Note: Session-scoped parser and can_parse trace selection

Status: proposed

English | [中文](2026-11-20-session-scoped-parser-can-parse.md)

## Problem

Session `226504ab-f005-42ce-a9f5-8313c45d669e` renders its three subagents as `synthetic-agent`: the envelope `agentMeta` lacks `toolUseId`, while the current `BaseTraceParser.normalize(payload)` handles one Agent JSONL at a time and `ClaudeCodeTraceParser` cannot see the other transcripts of the same root during normalization, so parent links fall back to weak fields in `agent_tree`. The user asked for Plan A — initialize the whole session's main/subagent traces into the subclass members at construction — and for parser selection to follow the trace, with a new `can_parse` deciding whether a subclass can initialize a trace ([issue #429](https://github.com/Shadow-Azure/harness-evolution/issues/429)).

The design documents still say `TraceParserFactory` selects by `runtime_key`, the parser normalizes one payload at a time, and a new runtime does not change public replay/agent_tree ([01 §4.1](../../../../plans/fullstack-design/01-architecture.md), [06 §3.0.1](../../../../plans/fullstack-design/06-database-design.md), [07 §2.6](../../../../plans/fullstack-design/07-backend-implementation.md)). Without revising them first, the implementation would directly contradict the design documents; this Note records that decision and why the documents change in the same PR.

## Decision

- Parser selection is driven by **trace content**: `BaseTraceParser.can_parse(payloads)` is an abstract class method for fast shape detection in each subclass; `TraceParserFactory.for_trace(payloads)` instantiates only on a unique match, raises `UnsupportedTraceRuntime` on zero matches and `AmbiguousTraceRuntime` on multiple, and never silently picks by registration order. `runtime_key` remains the runtime identity and storage key, no longer the sole selector.
- The parser lifecycle becomes **session-scoped**: the constructor receives every `TracePayload` of one root (the main Agent plus all nested subagents) and initializes `payloads` / `main` / `subagents` members; `normalize_session()` normalizes each payload and calls the subclass `link_transcripts()`, returning transcripts and `AgentLink`s in one call.
- Parent-link precedence: the envelope `toolUseId` is authoritative; when absent, the parent `toolUseResult.agentId` ↔ child JSONL top-level `agentId` yields a derived link; missing or ambiguous links keep `synthetic`. `agent_tree` only applies links and reads no Claude-private fields.
- The three entry points (replay / local / normalize) load all payloads of a root first, create the session parser with `for_trace`, then call `normalize_session`; single-payload `normalize(payload)` stays as a compatibility entry.
- Lifecycle and memory: one parser instance per root holding references to the already-loaded payloads, without copying raw JSONL; release after `normalize_session`, never reuse across roots, and add no cross-request cache.
- Revise [01 §4.1](../../../../plans/fullstack-design/01-architecture.md), [02 F9](../../../../plans/fullstack-design/02-features.md), [04 parser extension point](../../../../plans/fullstack-design/04-backend-architecture.md), [05 envelope](../../../../plans/fullstack-design/05-api-design.md), [06 §3.0.1/§7.1](../../../../plans/fullstack-design/06-database-design.md), [07 §2.3/§2.5/§2.6](../../../../plans/fullstack-design/07-backend-implementation.md), [09 R10/R17](../../../../plans/fullstack-design/09-review-guide.md), [15 multi-runtime gap](../../../../plans/fullstack-design/15-v1-v2-gap-analysis.md), and [README D24](../../../../plans/fullstack-design/README.md) in the same change; implementation is tracked by #429.

## Alternatives considered

- **Plan B: stateless parser plus a session-level link hook.** The smallest change and no full payload retention, but it only fixes parent links and does not realize the requested "initialize the whole session into members at construction"; the user explicitly switched to Plan A, so it is rejected.
- **Keep runtime_key selection and use can_parse only as validation.** Selection still cannot handle a missing/mislabeled runtime_key or multiple trace shapes within one runtime, which contradicts "select by trace"; rejected.
- **Constructor-inject members without can_parse.** The lifecycle matches Plan A, but selection still depends on the caller-supplied runtime_key and cannot satisfy "decide from the trace whether it can initialize"; rejected.
- **Per-payload parser plus a SessionContext.** Closer to the session model than B, but the parser is still not "session at construction" and the requested member semantics do not hold; it also changes the shared orchestration, so the session-scoped constructor is simpler; rejected.

## Consequences

- Design documents and the implementation contract agree: selection, lifecycle, and link precedence no longer disagree; the implementation PR follows #429.
- The parser API changes: `__init__(payloads)`, `can_parse`, `normalize_session`, and `for_trace`; `create(runtime_key)` and `normalize(payload)` become explicit/compatibility entries, and current callers migrate per #429.
- Each root's parser holds references to all payloads; a large session's peak memory is bounded by the already-loaded payloads, with no extra copy; the parser is not reused across roots.
- Selection errors expand from "unknown runtime" to "unknown trace/ambiguous trace"; implementation must stabilize the error codes and diagnostics.
- Existing roots need a `parser_version` bump followed by replay/backfill; no database schema, shared contract, or frontend change.
- In 01 §4.1, "a new runtime does not change public replay/agent_tree" becomes "the shared session orchestration is generic and a new runtime only implements subclass hooks"; a new runtime still implements `can_parse` and session links.
