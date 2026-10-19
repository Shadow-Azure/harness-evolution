# Evolution loop

English | [中文](m3-evolution-loop.md)

```yaml flow
kind: milestone
id: m3
title: 自进化闭环
status: planned
github:
  number: 4
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/4
```

## Goals

Attribute diagnosed problems to skill / prompt / tools / control flow, generate minimal-change proposals, and use comparative evaluation to adopt or roll back.

## Acceptance

- At least one real problem completes "diagnosis → proposal → comparative verification → adopt or reject".
- Experiment records include baseline, treatment, metrics, budget and decision rule.
- Adoption or rejection can roll back through a version or switch.

## Issues

- [Improvement proposal generation and attribution](../issues/m3-01-improvement-proposal.en.md)
- [Comparative evaluation and adoption decision](../issues/m3-02-comparative-eval.en.md)
