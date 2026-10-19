# Prototype contracts and session-family snapshot loading

English | [中文](m1-contracts-snapshot-loader.md)

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - packages/contracts/**
  - apps/web/src/prototype/**
  - scripts/**
  - tests/**
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 10
  url: https://github.com/Shadow-Azure/harness-evolution/issues/10
```

## Background

Codex subagents write separate rollouts while the root session remains the user's entry point. Reading one JSONL misses child-agent execution and evidence, and `session_id` may be reused by child rollouts, so it cannot serve as a stable key.

## Goals

- Define contracts for SessionFamily, AgentNode, SkillUse, TimelineItem, Finding, AttributionTarget and EvidenceRef.
- Build a local snapshot loader that starts from four root rollouts and recursively discovers every descendant by parent_thread_id.
- Use rollout file identity as the primary key and retain parent, depth, agent path and nickname.
- Index metadata only and lazily load one rollout; raw JSONL never enters the repository.

## Acceptance

- The four families contain 64 rollouts, 25,170 records and roughly 72.2MB, with maximum depth four.
- The family index restores parentage without losing agents whose rollouts reuse session_id.
- The loader reads individual rollouts on demand and does not parse all 72.2MB at startup.
- Snapshots include at least three cross-agent example findings with stable evidence anchors.
- Every finding resolves to an attribution target id and name of type `skill` or `agent`.
- Raw JSONL stays local and gitignored; committed fixtures are redacted or derived.
- Contract and loader tests pass along with type checking and documentation gates.
