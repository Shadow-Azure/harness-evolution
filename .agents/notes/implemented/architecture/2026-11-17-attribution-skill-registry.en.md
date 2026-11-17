# Agent Note: Immutable Attribution Skill Versions and Three-Level Binding

Status: implemented

English | [中文](2026-11-17-attribution-skill-registry.md)

## Problem

When an attribution method is selected only by a global engine switch or mutable content on a target, two targets cannot safely choose different methods and configuration edits change the meaning of historical runs and caches. Platform, workspace, and target overrides also lack explicit precedence.

## Decision

An attribution Skill consists of a definition, append-only revisions, and bindings. A revision freezes controlled JSON content, its SHA-256, executor type, and output schema; a binding may reference only a published compatible revision. Resolution order is target binding, workspace default, then the protected platform default. Unbinding falls back and binding an older revision performs rollback. The migration seeds the platform default, which workspace APIs cannot disable. Run creation freezes the effective key, revision, and content hash, and report manifests use that snapshot instead of reading the current binding.

## Alternatives considered

Embedding Skill content directly in an evolution target was rejected because it mixes target-code configuration with attribution policy and overwrites history on every edit. Saving only a current-revision pointer was rejected because old runs would drift with bindings, so runs persist the effective identity. Uploading executable code would expand the supply-chain and secret boundary; this iteration stores only instructions, flow, and tool declarations interpreted by a platform executor.

## Consequences

Targets can bind revisions independently, workspaces can provide a shared fallback, and an unconfigured target still has a deterministic platform default. Disabling affects only future resolution; historical reports and runs remain readable. Skill keys are currently platform-unique to simplify cross-workspace reference protection; if same-name workspace Skills become necessary, identity must evolve to namespace/key while preserving stable manifest keys. The executor remains rule-based, and `agent_stub` and `agent` are registry metadata until the executor iteration delivers real invocation.
