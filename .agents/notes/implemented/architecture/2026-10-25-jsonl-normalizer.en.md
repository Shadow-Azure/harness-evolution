# Agent Note: JSONL Normalization Boundary

Status: implemented

English | [中文](2026-10-25-jsonl-normalizer.md)

## Problem

Claude Code raw JSONL mixes user input, assistant fragments, tool calls, tool results, hidden thinking, usage, and provider control records. Persisting those records directly would duplicate large messages, expose internal reasoning, and make statistics drift with streaming fragments.

## Decision

Per-payload normalization is a pure function, with parser version starting at `1`. A bad line or a valid JSON value that is not an object produces a stable, sanitized issue and does not stop later lines. Assistant messages deduplicate by `message.id`, and the last observed cumulative usage wins across streamed fragments; token totals include only input and output counters. Tool counts include only `tool_use` while retaining its `tool_use_id` association, and the real provider's `server_tool_use` is excluded under the current contract; error counts include every content block with `is_error=true`. The node model is the most frequent non-empty assistant model, with first occurrence breaking ties, while every model remains available for later session aggregation.

Only string or textual-array user input from the main agent, plus `type=attachment` records carrying the real `origin.kind=human` or compatible `queued_command.origin.kind=human` shape, creates user turns. Metadata, tool results, four control-message prefixes, other origins, and control records that merely resemble attachments do not. Every retained user turn must have a valid timestamp; a missing or invalid value creates a stable sanitized issue and skips that turn, avoiding data that cannot satisfy the non-null timestamp column. Skill, Agent, and Workflow tool calls create events that retain the trigger tool id, name, description, one-based line number, and zero-based unique-assistant-message offset. The parse result keeps a recursively frozen copy of raw `agent_meta` for tree assembly and retains structural block identities outside user turns; messages, thinking, and tool-result text live only during parsing and never enter public results or persisted fields.

In m2-03, normalization emits only statistics and anchors. Agent-tree assembly, business-table rewriting, and `source_records.processed_*` updates remain with m2-04 and m2-05. A repository appends parse issues to a supplied `sync_runs.errors`, retaining only session/agent/line/code/message.

## Alternatives considered

- Persist complete messages and content blocks: this violates the decision to remove the timeline and expands privacy and storage exposure.
- Fix usage to the first streamed assistant fragment: real streams often publish the cumulative value in a later fragment, undercounting the entire message to zero or a partial value.
- Fold `server_tool_use` into the tool total: the authoritative design currently counts only `tool_use`; changing that needs separate design review.
- Drop an entire file after invalid identity or JSON: this turns one provider anomaly into whole-file data loss and contradicts line isolation.

## Consequences

The fixture manifest is now the normalizer's golden oracle, and tests reject payload/manifest drift. Later M2 work must use the same parser and version to assemble trees and update processing cursors, incrementing `CURRENT_PARSER_VERSION` whenever derivation semantics change. New provider tool or message shapes require compatibility tests and design records rather than silent statistic changes.
