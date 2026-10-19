# Trace visibility

English | [中文](m1-trace-viewer.md)

```yaml flow
kind: milestone
id: m1
title: 轨迹可查看
status: planned
github:
  number: null
  url: null
```

## Goals

Import real sessions from local Codex rollouts, show messages, reasoning, tool calls, outputs, errors and tokens turn by turn, and locate any tool call from the timeline.

## Acceptance

- One real Codex session can be scanned and incrementally imported.
- The SQLite schema, repository and migrations run.
- The web app opens session detail and locates any tool call.

## Issues

- [Codex rollout scanning and incremental ingest](../issues/m1-01-rollout-ingest.en.md)
- [Session list and turn timeline](../issues/m1-02-session-timeline.en.md)
