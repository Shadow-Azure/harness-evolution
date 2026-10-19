# Agent Note: Session family prototype and cross-agent analysis

Status: proposed

English | [中文](2026-10-19-session-family-prototype.md)

## Problem

Codex subagents write separate rollouts, but users analyze from the root conversation. Treating one rollout as a complete session misses child-agent execution, skill usage and failure evidence. Simply concatenating transcripts loses parentage, agent paths and stable anchors.

## Decision

- A session family is the first-class analysis scope: the root rollout plus every descendant subagent, assembled recursively by `source.subagent.thread_spawn.parent_thread_id`.
- Rollout file identity is the primary key; `session_id` is unsafe because child rollouts may reuse the parent conversation's `session_id`.
- M1 uses four real root families as prototype samples: 64 rollouts, 25,170 records, roughly 72.2MB, maximum depth four.
- M1 builds a local snapshot adapter and frontend experience without SQLite or the API; raw JSONL never enters the repository.
- Diagnosis extracts evidence per agent, then the root agent merges, deduplicates and synthesizes cross-agent findings. Evidence retains rollout, agent path, line and item or call id.
- M1 stubs findings, attribution and evolution data; the validation platform is simulated through an API contract and performs no real changes.
- The demo path is fixed: session search → execution flow → finding → attribution explanation → evolution simulation → validation metrics → accept or reject.
- The root agent and every child agent share one execution-flow diagram whose nodes carry state, finding counts and evidence entry points.
- Root and child-agent findings share one family-level list, distinguished by source labels rather than separate views.
- Every attribution names a target type and target id (skill or agent); evolution aggregates findings for that target and simulates training/improvement.
- "Training" in M1 means harness-level improvement simulation, not model-weight training.

## M1 snapshot contract implementation

- The index reads only the first `session_meta` line of each rollout; bodies are loaded per thread on demand and raw JSONL never enters the repository.
- `threadId` (`payload.id`) is the agent key, `rolloutId` (relative path) distinguishes segments, and `sessionId` is display-only.
- Continuation segments share one `AgentNode` with the primary segment; primary and continuation record counts are reported separately.
- Guardian review threads stay outside the Session Family; their files remain in the original directory and can be read independently.
- `TimelineItem` is the stable envelope for commands, file changes, MCP calls, collaboration calls, subagent activity, and token usage; duplicate `event_msg.item_completed` and `response_item` entries are removed by id/call_id.
- Browser wiring is out of scope for #10; #14/#15 decide how the snapshot reaches the frontend.

## Alternatives considered

- Treat each subagent as an independent session: easy to implement, but cannot explain why the root task failed; rejected.
- Concatenate all rollouts into one timeline: loses agent ownership and makes duplicate IDs and call relationships hard to recover; rejected.
- Use `session_id` as the unique key: child rollouts already reuse the parent ID and would overwrite data; rejected.
- Connect the prototype directly to SQLite and the API: slower feedback and couples visual validation to the data pipeline; rejected.

## Consequences

- The snapshot loader must recursively build a family index and lazily load individual rollouts.
- The timeline needs virtualization, per-agent filtering and parent-child navigation.
- SQLite must persist parent rollout, depth and agent path, and analysis jobs enter through the root rollout.
- Cross-agent conclusions must deduplicate and let users expand a root finding into evidence from each related child agent.
- The prototype must label stubbed data and distinguish simulated validation from real platform calls.
- The execution diagram and attribution target must share stable ids so navigation from a child-agent finding to target aggregation never breaks.
