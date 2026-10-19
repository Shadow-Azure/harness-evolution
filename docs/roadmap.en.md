# Roadmap

English | [中文](roadmap.md)

## M0 Scaffold (done)

- pnpm workspace
- React + Vite web app
- Fastify + TypeScript server
- Shared contracts package
- Health check wired across both ends

## M1 Frontend experience prototype (current)

- Four real Codex root sessions with every descendant subagent included
- Search and switch sessions; inspect an execution-flow diagram covering the root agent and every subagent
- Local snapshot adapter without SQLite or the API
- Show root and child-agent findings together in one panel, then attribute each to a specific skill or agent
- Aggregate findings by target skill or agent and simulate evolution/training plus validation metrics
- One complete demo path from finding to accept or reject

Acceptance: locate a child-agent finding from the execution-flow diagram, attribute it, select a target skill or agent, run one simulated evolution over that target's findings, and accept or reject the result.

## M2 Codex trace service

- Stream rollouts and assemble session families by parent_thread_id
- Incremental import, SQLite schema and repository
- Session, family, ingest and timeline APIs
- Replace prototype snapshots with the real data source

Acceptance: the four root families import idempotently and the web app matches the prototype.

## M3 AI trace diagnosis

- Rule diagnosis: tool failures, repeated retries, unverified edits, unclosed errors
- Analyze each agent first, then let the root agent synthesize cross-agent findings
- AI emits structured findings, evidence and improvement suggestions
- Diagnosis job state and history
- Findings linked back to traces

Acceptance: one root analysis covers every descendant subagent, and evidence carries the agent path and remains navigable.

## M4 Evolution loop

- Attribute problems to skill / prompt / tools / control flow
- Aggregate attributed problems by skill or agent
- Generate minimal-change proposals
- Comparative evaluation and adoption/rollback records

Acceptance: at least one real problem completes "diagnosis → proposal → comparative verification → adopt or reject".
