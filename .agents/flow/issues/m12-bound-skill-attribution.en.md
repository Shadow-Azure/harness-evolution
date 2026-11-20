# Target-bound attribution skills, background analysis and report reuse

English | [中文](m12-bound-skill-attribution.md)

```yaml flow
kind: issue
id: m12-27
milestone: m12
depends:
  - m12-26
priority: P0
status: done
scope:
  - apps/**
  - packages/contracts/**
  - plans/**
  - .agents/**
  - docs/**
  - tests/**
  - scripts/**
  - deploy/**
  - .gitignore
  - package.json
adr:
  - ../../notes/implemented/feature/2026-11-18-attribution-skill-package-admin.md
github:
  number: 417
  url: https://github.com/Shadow-Azure/harness-evolution/issues/417
```

## Background

Workspace packages and per-run attribution currently have different activation paths.

## Goals

Bind one package per target and share latest case reports with evolution.

## Design authority

[Evolution design](../../../plans/fullstack-design/02-features.md#对象绑定归因)

## Implementation

Persist target binding, batch intent, report provenance and latest-per-case counts.

## Implementation steps

Implement durable background attribution, run-scoped selection, resource detail, and prototype.

## Dependencies and boundary

Reuse the local agent and canonical report writer delivered in m12-26.

## Verification

Run pnpm test:api and pnpm test. Exercise a synthetic target with two reports for the same case.

## Acceptance

The preview counts the latest report once. Recompute preserves the target binding.

## Gates and CI

API and Web tests, generated contracts, type checks and prototype screenshot comparison.

## Non-goals

Model provisioning and downstream clustering algorithms.
