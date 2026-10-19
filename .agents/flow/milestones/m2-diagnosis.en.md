# Trace diagnosis

English | [中文](m2-diagnosis.md)

```yaml flow
kind: milestone
id: m2
title: 轨迹诊断
status: planned
github:
  number: null
  url: null
```

## Goals

Use rules and AI to detect goal drift, tool failures, repeated retries, unverified edits and unclosed errors, with every finding linked back to evidence.

## Acceptance

- Rule diagnosis produces structured findings and evidence locations.
- AI diagnosis uses shared contracts to emit findings, evidence and improvement suggestions.
- Clicking evidence in the findings list jumps to the corresponding trace.

## Issues

- [Rule diagnosis and evidence location](../issues/m2-01-rule-diagnosis.en.md)
- [AI diagnosis and structured output](../issues/m2-02-ai-diagnosis.en.md)
