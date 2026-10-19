# Session list and turn timeline

English | [中文](m1-02-session-timeline.md)

```yaml flow
kind: issue
milestone: m1
priority: P1
status: backlog
scope:
  - apps/web/**
  - apps/server/src/sessions/**
  - packages/contracts/**
  - docs/architecture.*
  - .agents/notes/**
adr: []
github:
  number: null
  url: null
```

## Background

Imported traces need a readable interface: goals, messages, reasoning, tool calls, outputs, errors and tokens by turn, with the ability to locate any tool call.

## Goals

- Provide session list and detail APIs.
- Render the timeline by turn with expansion and location support.
- Handle empty states, load failures and large sessions explicitly.

## Acceptance

- A real Codex session opens in the web app.
- Clicking any tool call shows the full input, output and error.
- List and detail fields come from shared contracts.
