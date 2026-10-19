# M4 Evolution loop: skill and agent improvement evaluation

English | [中文](m4-evolution-loop.md)

```yaml flow
kind: milestone
id: m4
title: M4 自进化闭环：Skill 与 Agent 改进评测
status: planned
github:
  number: 8
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/8
```

## Goal

Turn real findings into evidence-backed, reversible harness improvements.

## Scope

- Aggregate attributed findings by skill or agent
- Generate minimal-change proposals bound to original evidence
- Comparative evaluation, guardrail metrics and adoption/rollback records

## Acceptance

- At least one real problem completes "diagnosis → proposal → comparative verification → adopt or reject"
- Evolution must start by selecting a target skill or agent and show its finding set
- Every proposal traces back to its finding, session family and exact evidence
- Adoption and rollback both have version identifiers and evaluation results

## Non-goals

- Model-weight training
- Automatic merges without evaluation evidence
