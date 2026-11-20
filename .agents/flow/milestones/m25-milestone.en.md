# M25 Session-level trace parent links

English | [中文](m25-milestone.md)

```yaml flow
kind: milestone
id: m25
title: M25 轨迹父子关系会话级链接
status: planned
github:
  number: 35
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/35
```

## Goals

Move cross-agent parent links back into a session-level parser interface: the base class defines the link hook, `ClaudeCodeTraceParser` implements it with Claude agent-id evidence, and `agent_tree` only applies the result instead of guessing runtime details in the generic assembler.

- Fix the case where a child agent becomes a `synthetic-agent` and its lane piles up at the end when the envelope `agentMeta` lacks `toolUseId`.
- Let a new runtime implement only the subclass link hook without adding runtime branches to shared replay / agent_tree.
- Keep the `synthetic` fallback for missing or ambiguous links, never inventing a parent.

## Scope

`apps/api/app/service/acquisition/` (the `parsers/` package and `agent_tree`), the session-level wiring, focused API tests and browser acceptance; matching updates in `docs/`, `plans/`, `.agents/flow/`, and an Agent Note.

## Acceptance

- In a fixture shaped like session 226504ab, the three subagents attach to the real `call_…` triggers; the tree and lane DAG no longer show `synthetic-agent`, and the child lanes start at L1028 / L1202 / L1411.
- The base link hook defaults to empty; runtimes that do not implement it behave unchanged, and the `synthetic` fallback still covers missing and ambiguous links.
- After `parser_version` is raised and replay runs, existing roots rebuild their `agents` / `agent_events`; no new database column, contract field, or frontend change.
- Focused unit tests, API tests, and flow/document gates pass; the PR includes before/after captures from the real application.

## Non-goals

Do not change the eval-platform envelope projection or `toolUseId` forwarding; do not change the frontend lane DAG / tree algorithms; do not add database schema or shared contract fields; do not commit production session content, screenshots, or credentials.
