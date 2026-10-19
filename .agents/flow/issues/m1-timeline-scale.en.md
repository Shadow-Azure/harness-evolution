# Long-trace virtualization and heavy-payload fallbacks

English | [中文](m1-timeline-scale.md)

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
  number: 16
  url: https://github.com/Shadow-Azure/harness-evolution/issues/16
```

## Background

The four selected families contain 25,170 records and roughly 72.2MB of raw payload. Individual files exceed 20MB and a single tool output approaches 800KB, so rendering every event at once would make the prototype unusable.

## Goals

- Lazily load by turn and virtualize long lists.
- Summarize large tool outputs, MCP results and images with on-demand expansion.
- Keep raw JSONL and the full fixture out of the initial frontend bundle.
- Preserve scroll position, selected agent and evidence location.

## Acceptance

- A 25,170-record family becomes interactive on first paint without rendering every event.
- Root sessions above 3,000 records scroll continuously and segment by turn.
- Large tool outputs show a summary until explicitly expanded.
- Images show paths and thumbnail placeholders without blocking the timeline.
- Evidence jumps keep scroll position stable and avoid full reflow.
