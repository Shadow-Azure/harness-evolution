# Agent Note: Multi-runtime trace parsers and lane DAG execution flow

Status: proposed

English | [中文](2026-11-16-runtime-parser-and-lane-dag.md)

## Problem

The normalizer hard-codes Claude Code record, metadata, and event semantics. `source_type` is also treated as a runtime, and `parser_version` is a global integer. Adding a second AI agent would force more conditionals in `normalize.py` and changes to replay, uniqueness, and version checks. Separately, the V2 prototype has moved the execution flow to a small-window lane DAG, while the design docs and M11 still describe a Vue Flow node tree, `>8` folding, and filtering by problem; no issue owns the layout migration.

## Decision

Use `runtime_key` to identify the AI agent and keep `source_type` for the ingestion channel. `TraceParserFactory` selects a `BaseTraceParser` subclass by `runtime_key`; the base class owns JSONL framing, bad lines, privacy, counters, and finalization, while subclasses interpret records, metadata, events, and evidence. Interpret `parser_version` per runtime, and let a new runtime add only a subclass and registration. For execution flow, default to a lane DAG: log-line intervals, `A1/A1.1` depth, cross-lane concurrency, all lanes expanded, and small-window zoom/pan. Keep the structure tree as a toggled view; selection keeps all branches and highlights the matching case.

## Alternatives considered

Adding `runtime == ...` branches to one `normalize_transcript` spreads provider differences into shared flow and tests. Using `source_type` as the runtime conflates ingestion with agent type. Rendering 56 lanes as a Vue Flow node tree reintroduces folding, filtering, and clipping; expressing selection by filtering also hides concurrency.

## Consequences

M9 gains a runtime-parser prerequisite and M11 gains a lane DAG slice; M9-01/02/04 and M11-02/05 must be updated. The change surface for a new runtime shrinks to a parser subclass, a fixture, and registration tests, with no replay/agent_tree changes. Unknown runtimes fail fast rather than falling back to Claude. The small viewport and expanded lanes require more viewport interaction but avoid hiding concurrency. This PR updates design and flow drafts only; `flow:sync` runs after review, and GitHub numbers for new issues are backfilled then.
