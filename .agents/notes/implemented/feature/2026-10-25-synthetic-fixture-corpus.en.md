# Agent Note: Synthetic Fixture Corpus

Status: implemented

English | [中文](2026-10-25-synthetic-fixture-corpus.md)

## Problem

Later M2 parsing, query, and presentation work all need a repeatable, small development dataset that contains no real traces. Constructing in-memory objects only in tests would separate runtime paths, database constraints, and demo data, and could not prove that frontend or API reads use production-shaped tables.

## Decision

`fixtures/m2-synthetic/` stores four deterministic Agent session trees, one JSONL payload per agent, issue and attribution records, and target configuration. The manifest uses a closed Pydantic schema; payload paths must remain inside the corpus, SHA-256 hashes and line counts derive from raw bytes, per-file and total byte budgets apply, and local real-path or secret markers are rejected.

In demo or test environments, seed runs Alembic to create foundational domain tables and then upserts payloads, processing indexes, sessions, agents, trigger events, user turns, issues, attribution, and evolution targets by stable key in one transaction. The full corpus validates before writes; unchanged repeated runs write nothing, while changed source fields update in place without replacing stable IDs. Existing source processing state and `last_sync_run_id`, plus the administrator assigned to an existing evolution target, are runtime-owned and remain untouched by repeated seeds; `created_by` initializes only when the target is inserted. `fixtures:check` provides static validation without a database, while CI runs both check and seed.

## Alternatives considered

- Build objects only in test code: this bypasses real tables, migrations, and unique constraints and cannot serve demo data.
- Treat JSON as a runtime data source: this introduces the design-forbidden stub provider and lets API and fixtures drift.
- Commit SQL or real sessions directly: this is hard to audit and risks local paths, credentials, or oversized private content.
- Create every evolution parent and derived cluster table in M2-01: this exceeds the slice, so later issues extend the same migration tree.

## Consequences

Later M2 issues must reuse `app.db.models.domain` and the same tables instead of introducing a second model. Fixtures currently contain structured metadata and raw JSONL, not persisted message or content-block detail; later synchronization must generate and verify stats from payloads. Revision `0004` freezes its tables, indexes, and foreign keys inside the migration; future schema changes require new Alembic revisions rather than edits to old migrations or mutable model metadata.
