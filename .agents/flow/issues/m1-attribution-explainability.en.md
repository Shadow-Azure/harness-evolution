# Finding attribution and inference explanation

English | [中文](m1-attribution-explainability.md)

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/web/src/**
  - packages/contracts/**
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 9
  url: https://github.com/Shadow-Azure/harness-evolution/issues/9
```

## Background

A list of findings is insufficient for evolution. Users must understand what happened, its impact, why the cause was inferred, and which skill or agent the problem should be attributed to. M1 validates the presentation with reviewed attribution snapshots; finding collection is discussed later.

## Goals

- Define contracts for FindingAttribution, AttributionTarget, CausalStep, InferenceStep and EvidenceRef.
- Open attribution details from a finding, leading with a plain-language summary and then the causal and inference chains.
- Link every inference step to evidence and distinguish confirmed, inferred and unknown parts.
- Show rejected candidate causes so users understand why other explanations were not adopted.
- Support cross-agent attribution with evidence contributed by the root agent and related subagents.
- State exactly one target skill or agent per attribution and explain why that target was chosen.

## Acceptance

- Every example finding explains "what happened and what impact it had" in non-technical language.
- Every finding shows its attribution target type, name, id and selection rationale.
- The causal chain has at least three layers: trigger, direct cause and final impact.
- Inference steps cite rollout, agent, turn or tool-call evidence that navigates on click.
- The page shows confidence, unproven parts and rejected candidate causes.
- Cross-agent findings expand into related subagents instead of presenting only a root conclusion.
- The page labels results as example attribution rather than live model inference.
