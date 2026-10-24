# Roadmap

English | [中文](roadmap.md)

The product advances through independently verifiable milestones; machine-readable status and issue dependencies live in [.agents/flow/roadmap.md](../.agents/flow/roadmap.en.md).

## M1 Engineering foundation and quality gates

Current phase. Deliver FastAPI, Vue 3, the dual-dialect data foundation, OpenAPI, identity, jobs/SSE and CI meta-gates.

Acceptance: an empty system supports login; static, data, contract and flow gates are enforced.

## M2 Trace data and normalization

Connect synthetic fixtures, local real traces, JSONL normalization, the agent session tree, idempotent replay, query APIs and incremental scheduling.

Acceptance: reprocessing one payload creates no duplicate business rows; malformed structures are isolated per record; query contracts cover lists, overviews and agent trees.

## M3 Session browsing and execution flow

Deliver the session list, overview, agent execution-flow graph, stable deep links and performance budgets.

Acceptance: users can enter a session from the list, locate root and child agents and trigger events in the graph, and return to the same node.

## M4 Problems and attribution

Connect external read-only bad_case/probe data and deliver problem APIs, cards and error details.

Acceptance: problems and attribution enter the execution flow from real read-only tables, with complete deep-link fields and cross-session validation.

## M5 Evolution loop

Deliver target configuration, run lists, the launch wizard, six-stage state, event logs, real git candidates and a placeholder patch/evaluation loop.

Acceptance: a run advances from preparing to final evaluation, blocked work is retryable, and every stage is recoverable from events and snapshots.

## M6 Real integration and delivery

Connect the real upstream trace source, external contracts, real patch evaluation and clustering upgrades.

Acceptance: real data and evaluation services replace development adapters, with live evidence for contracts and failure boundaries.
