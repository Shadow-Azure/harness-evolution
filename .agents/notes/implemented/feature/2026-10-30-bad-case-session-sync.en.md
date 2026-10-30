# Agent Note: scheduled bad-case root trajectory sync

Status: implemented

English | [中文](2026-10-30-bad-case-session-sync.md)

## Problem

`bad_cases.bad_case_session_id` points at the root session a problem belongs to, but this service does not guarantee that the root session's raw trajectory has entered `trajectory_payloads`. Ingestion previously had only local import and administrator-triggered pull, both requiring an operator who knows the session ids or the window; as bad_cases grows, problem detail, the execution-flow graph, and evolution launch can miss sessions when their payloads are absent. The query service only offers one-level direct-child enumeration and a per-agent NDJSON trajectory download, and the latter forbids concurrency, so the existing "one whole package per root" pull contract cannot be reused.

## Decision

Add a `bad_case_root_sync` status table and a `bad_case_root_sync` scheduled job: start from distinct `bad_cases` roots with a LEFT JOIN, select roots that are unsynced, retry-due, or lease-expired; after claiming, expand level by level through API 1 and fetch each agent's NDJSON serially through API 2; write `trajectory_payloads` (`source_type=http_api`, subagent `agent_meta={"parentAgentId": ...}`) and reuse shared replay. `synced` means the payload set is complete; replay failures stay in the existing sync audit and do not roll back status. The overlap policy is skip: a tick that sees an active `bad_case_root_sync` job submits nothing, one job is bounded by batch and time budget, and the next tick resumes from the status table; no queue, no cancel, no parallelism. A status row whose root disappeared from bad_cases remains audit-only and is excluded from current statistics; a new root without a status row counts toward `total` and `unsynced` and is selected by the candidate query.

## Alternatives considered

Queueing one follow-up job while active was rejected: the periodic tick is already the follow-up mechanism, and queueing only creates duplicate scans and jobs. Cancelling the previous job was rejected: written payloads are real progress and API 2 is serial, so cancellation wastes calls. Parallel jobs with per-root claims were rejected: API 2 forbids concurrency, parallelism buys no throughput and needs cross-process locks. Marking a root `synced` from an existing main payload row at launch was rejected because subagent completeness cannot be verified and the "synced" number would lie; the first run accepts one refetch and spreads it across bounded batches. Extending the existing whole-package pull was rejected because the query service does not return packages and carries no `agent_meta`, so a separate client is required.

## Consequences

The change adds a service-owned table, a migration, a job kind, settings, a status endpoint, and a top-nav display; production carries one more table, while manual pull stays unchanged. The first run also refetches roots that already have payloads; for a large history the batch and time budget spread it across ticks. Multi-instance deployment still needs a cross-process lock and a cross-process serialization primitive; this version is single-instance. Subagents have no `toolUseId`, so they can only anchor to the parent agent node through `parentAgentId`, which is less precise than local import; the existing pull's `parentToolUseId` / `toolUseId` mismatch is fixed in the same change. `agent_count` records the root's actual payload rows including main, is diagnostic only, and never participates in the synced statistic.
