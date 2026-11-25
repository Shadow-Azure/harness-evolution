# Preserve explicit Skill verdicts for external causes

English | [中文](bugfix-explicit-skill-conclusion.md)

```yaml flow
kind: issue
id: bugfix-56
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - attribute-badcases/**
  - apps/api/app/service/evolution/local_attribution.py
  - apps/api/tests/attribution/**
  - plans/evidence/attribution-verdict-588/*.png
  - .agents/flow/issues/bugfix-explicit-skill-conclusion*
  - .agents/notes/implemented/architecture/2026-11-17-attribution-report-v2*
adr: []
github:
  number: 588
  url: https://github.com/Shadow-Azure/harness-evolution/issues/588
```

## Background

A production report assigned the observed failure to an external scoring environment and identified a verification improvement in the selected Skill. Its source identity matched the selected object and its category was error. The stored affirmative conclusion was reused three times. Automated regression tests use synthetic data. The PR also shows the same production case in the report UI before and after the fix.

## Goals

Require each new Skill execution to decide whether the selected target caused this case and preserve external causes, gaps in evidence and improvement suggestions.

## Design authority

[Backend design §5.13 on attribution generation and caching](../../../plans/fullstack-design/07-backend-implementation.md).

## Implementation

The local executor introduced in PR #421 derives the conclusion from identity and category. A synthetic report passed the writer and canonical checks, persisted, and qualified for clustering. Require an explicit three-way verdict, derive the evaluated identity from the input and record the root cause separately.

## Implementation steps

Exercise the shared Claude provider in noninteractive mode, update platform instructions, built-in Skill, writer and persistence, then compare positive, negative and frozen-snapshot cases.

## Dependencies and boundary

Bound uploads and the built-in Skill use the platform writer. Completed batches and historical reports keep their records.

## Verification

Run `pnpm test:api -- tests/attribution/test_local_runtime.py` against isolated SQLite for four contrasting cases. Exercise the live CLI on synthetic inputs and on the production case exported to local SQLite.

The shared Claude provider completed a noninteractive built-in Skill run at the application timeout of 600 seconds, validated its report, persisted it in SQLite and reused it on a second run. Replaying an anonymized scoring excerpt with the new contract yielded inconclusive and two evidence references. A fresh run of swe-5a7e0d8d69419188a326 with traces from all eight Agents and caching disabled returned non_target with eight evidence references. The detail view displayed the persisted non-target verdict and the run had zero clustering candidates. The export did not include the original scoring-container traceback.

## Acceptance

The same evaluated target supports all three verdicts. An external cause with an improvement proposal yields non_target, insufficient evidence yields inconclusive, and only attributed qualifies for clustering. Detect missing or invalid verdicts from the new writer before persistence.

## Gates and CI

Run the attribution API tests, type checks, documentation and flow gates.

## Non-goals

Historical production reprocessing, production configuration changes and prose-based causal classification are outside scope.
