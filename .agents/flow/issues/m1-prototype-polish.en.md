# Prototype demo experience and acceptance closeout

English | [中文](m1-prototype-polish.md)

```yaml flow
kind: issue
milestone: m1
priority: P1
status: backlog
scope:
  - apps/web/src/**
  - apps/web/index.html
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 13
  url: https://github.com/Shadow-Azure/harness-evolution/issues/13
```

## Background

The prototype must support real review and align later implementation. Beyond the main flow, it needs responsive behavior, keyboard operation, state feedback and demo guidance so edge cases do not interrupt review.

## Goals

- Complete desktop and narrow layouts with a clear three-column hierarchy.
- Cover loading, empty, parse-failure and no-findings states.
- Support keyboard switching among sessions, agents and finding evidence.
- Provide a demo script and acceptance screenshots.

## Acceptance

- The main flow works at 1440px and 1024px widths.
- Every button and interactive card has hover, focus and disabled states.
- The four complex samples follow a fixed demonstration path.
- README or demo notes list startup, sample scope and known limits.
- Prototype review requires no developer narration for key interactions.
