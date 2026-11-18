# Attribution skill registry, revision resolution, and target binding

English | [中文](m12-attribution-skill-registry-binding.md)

```yaml flow
kind: issue
id: m12-15
milestone: m12
depends:
  - m7-07
  - m12-14
priority: P0
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 320
  url: https://github.com/Shadow-Azure/harness-evolution/issues/320
```

## Background

The platform must select different attribution methods for different evolution targets, but it currently has only the global `HE_ATTRIBUTION_ENGINE` and no attribution-skill identity, immutable revision, target binding, or default fallback. Embedding skill content directly in a target or run request would make historical runs irreproducible and let unbind or rollback operations change old report meaning.

## Goals

- Provide one resolution order across platform Default Attribution Skill, workspace default, and target override.
- Persist immutable skill revisions, content hashes, executor types, and output-schema compatibility.
- Snapshot the effective skill revision on every run and Probe Report so current configuration cannot alter history.

## Design authority

- [06 §5.1–5.2](../../../plans/fullstack-design/06-database-design.md): evolution targets and run snapshots.
- [05 §4.11](../../../plans/fullstack-design/05-api-design.md): evolution-target configuration APIs.
- [07 §5.13](../../../plans/fullstack-design/07-backend-implementation.md): the pure attribution-engine boundary.

## Implementation

- Add skill-definition, immutable-revision, and target-binding storage; the platform default skill can be referenced but not deleted.
- Implement `AttributionSkillResolver` with target binding, workspace default, and platform default precedence.
- Support publish, disable, unbind, rollback, and referenced-revision deletion protection; historical revisions remain read-only.
- Limit skills to controlled instructions, procedures, and tool configuration rather than uploaded executable code; secrets remain environment-injected.
- Write the effective skill key, revision, and content hash into run and attribution execution manifests.

## Implementation steps

1. Write tests for resolution precedence, immutable revisions, unbind, and reference protection.
2. Implement migrations, repositories, resolver, and management APIs.
3. Connect run creation and attribution execution-manifest snapshots.
4. Add dual-database, RBAC, contract, and migration verification.

## Dependencies and boundary

- Depends on: m7-07 and m12-14.
- Boundary: deliver backend registration, revisioning, resolution, and binding; m12-19 delivers the complete configuration UI.

## Verification

```sh
pnpm test:api -- tests/attribution_skills
pnpm test:db
pnpm test:db:mysql
pnpm contract:check
```

- Target override, workspace default, and platform default fall back in order and return a stable revision and hash.
- A revision referenced by a historical run cannot be deleted, and unbinding does not change historical snapshots.

## Acceptance

- Two targets can bind different skill revisions and produce isolated execution manifests and cache identities.
- Unbinding a target falls back to the workspace or platform default; disabling a skill does not break historical reads.
- Unpublished or schema-incompatible revisions cannot be selected for a new run.

## Gates and CI

- API, dual-database, RBAC, contract, documentation, and Flow gates.

## Non-goals

- Do not execute arbitrary code plugins or build an online skill-body editor or external marketplace.
- Do not call a model, assemble Session traces, or decide attribution conclusions.
