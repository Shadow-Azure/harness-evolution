# AI diagnosis and structured output

English | [中文](m2-02-ai-diagnosis.md)

```yaml flow
kind: issue
milestone: m2
priority: P1
status: backlog
scope:
  - apps/server/src/analysis/**
  - packages/contracts/**
  - docs/**
  - .agents/notes/**
adr: []
github:
  number: null
  url: null
```

## Background

Rules cannot cover goal drift and verification gaps. The model must diagnose with full context while keeping output structured, traceable and reproducible.

## Goals

- Define input trimming and evidence-citation rules for diagnosis.
- Validate model output against a schema before storage.
- Record model, parameters, latency and retry failures.

## Acceptance

- Invalid model output is rejected and retryable.
- Every AI finding cites at least one real trace evidence item.
- Diagnosis records are reproducible and carry a budget cap.
