# Roadmap

English | [中文](roadmap.md)

## M0 Scaffold (current)

- pnpm workspace
- React + Vite web app
- Fastify + TypeScript server
- Shared contracts package
- Health check wired across both ends

## M1 Codex traces visible

- Scan local Codex rollout JSONL
- Incremental import
- SQLite schema and repository
- Session list and detail
- Messages, reasoning, tool calls, outputs, errors and tokens by turn

Acceptance: a real Codex session opens in the web app and any tool call can be located.

## M2 AI trace diagnosis

- Rule diagnosis: tool failures, repeated retries, unverified edits, unclosed errors
- AI diagnosis: structured findings, evidence and improvement suggestions
- Diagnosis job state and history
- Findings linked back to traces

Acceptance: the web app shows a session's findings and clicking evidence jumps to the corresponding trace.

## M3 Evolution loop

- Attribute problems to skill / prompt / tools / control flow
- Generate minimal-change proposals
- Comparative evaluation and adoption/rollback records

Acceptance: at least one real problem completes "diagnosis → proposal → comparative verification → adopt or reject".
