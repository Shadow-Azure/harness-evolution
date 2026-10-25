# Agent Note: Idempotent agent-tree replay

Status: implemented

English | [中文](2026-10-25-idempotent-replay.md)

## Problem

A session tree spans multiple Agent payloads under one root. Rewriting only an individual Agent can temporarily break parent edges, session aggregates, and user turns; a global high-water mark also misses changed content and parser upgrades.

## Decision

Pending records are determined by each source record's `processed_hash` and `parser_version`, then grouped by `root_session_id`. Before writing, replay loads every current root payload and runs the pure normalizer and Agent-tree assembler. Only a successfully assembled tree opens one root transaction. The transaction deletes old derived rows in foreign-key-safe event, Agent, user-turn, session order, writes the current canonical snapshot, and advances every current source cursor for that root; the cursor update syncs the current payload's `line_count/kind/source_type` while preserving the source `id/received_at`.

Payloads whose hash and parser version are unchanged do not become pending. A repeated batch records skips without refreshing processed time. A parser upgrade rewrites the whole root even when the hash is unchanged. Structural failure preserves the old tree and that root's cursors while other roots complete independently. Recoverable bad lines still write a tree and append stable sanitized issues to `sync_runs.errors`. `trajectory_payloads` remains read-only; replay does not delete existing business trees when a source file disappears.

## Alternatives considered

- Delete and rewrite one Agent at a time: this breaks version consistency for cross-Agent edges and session aggregates.
- Use a global processed high-water mark: it cannot represent the composite cursor and misses older parser versions.
- Clear the old tree before structural validation: users would see an unrecoverable hole instead of waiting for payload repair.
- Refresh processed time on every replay: unchanged input would create false write evidence and break the idempotency audit.

## Consequences

m2-06 and m2-07 can wrap this service with an API, sync lock, and scheduler without duplicating delete-rewrite rules. The m5 run-event projection remains separate. A replay parses the full root in memory, so cost grows with Agent count; the V1 single-organization serial boundary accepts that cost until scale requires an incremental index.
