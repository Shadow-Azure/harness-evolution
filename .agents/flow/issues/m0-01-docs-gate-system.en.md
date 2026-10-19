# Documentation, review and flow gate system

English | [中文](m0-01-docs-gate-system.md)

```yaml flow
kind: issue
milestone: m0
priority: P0
status: done
bootstrap: true
scope:
  - AGENTS.md
  - README.*
  - docs/**
  - .agents/**
  - plans/**
  - scripts/**
  - .github/**
  - .gitattributes
  - package.json
  - tsconfig.json
  - apps/**
  - packages/**
adr:
  - ../../notes/implemented/process/2026-10-19-docs-gate-system.md
github:
  number: null
  url: null
```

## Background

The repository had only a web and server scaffold, with no mechanical constraint on docs, flow or review; phase goals and task boundaries drifted into conversations.

## Goals

- Establish docs layering, bilingual trios, Agent Notes and postmortem structure.
- Establish the roadmap → milestone → issue flow tree, state machine and GitHub sync tooling.
- Establish doc-quick / doc-sync gates, CI wiring and local hooks.
- Port the PR review and Computer Use skills.

## Acceptance

- `pnpm lint:docs`, `pnpm verify:docs` and `pnpm verify:flow` are green.
- Five skills live under `.agents/skills/`, and the review standard lives in `docs/review.md`.
- The CI static lane runs documentation gates; the PR lane runs flow diff checks.
