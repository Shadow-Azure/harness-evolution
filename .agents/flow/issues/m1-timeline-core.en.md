# Turn timeline core rendering

English | [中文](m1-timeline-core.md)

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/web/src/**
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 15
  url: https://github.com/Shadow-Azure/harness-evolution/issues/15
```

## Background

Complex sessions mix user messages, reasoning, agent messages, commands, file changes, MCP calls, subagent activity and errors. Users need to follow the task by turn instead of scanning an unstructured event stream.

## Goals

- Render the timeline grouped by turn.
- Provide dedicated cards for user, agent, reasoning, tool call, tool output, file change, error and token events.
- Pair tool calls and outputs by call_id.
- Support collapsing, copying and raw-payload inspection for long text.

## Acceptance

- Every turn and event in a root session is browsable.
- Tool calls and outputs never mismatch, and failure state plus exit code remain visible.
- User messages and final agent replies are easy to locate in long traces.
- Long outputs collapse by default and expand on demand.
- Turn boundaries, timestamps and durations remain consistent.
