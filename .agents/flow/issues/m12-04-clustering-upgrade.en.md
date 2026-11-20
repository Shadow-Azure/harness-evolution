# Clustering algorithm upgrade

English | [中文](m12-04-clustering-upgrade.md)

```yaml flow
kind: issue
id: m12-04
milestone: m12
depends:
  - m10-04
  - m12-24
priority: P1
status: done
scope:
  - apps/api/**
  - fixtures/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 245
  url: https://github.com/Shadow-Azure/harness-evolution/issues/245
```

## Background

M12 carries forward the clustering work scoped in M6 issue #64. The design sections below define the implementation.

## Goals

Deliver clustering that can be verified independently. Keep contracts, database behavior and the frontend consistent for failures, empty inputs and retries.

## Design authority

- [07 §5.5 Clustering](../../../plans/fullstack-design/07-backend-implementation.md)
- [06 §5.3 probe_clusters](../../../plans/fullstack-design/06-database-design.md)
- [09 R11](../../../plans/fullstack-design/README.md)

## Implementation

Persist cluster assignments in `probe_clusters` and `probe_cluster_probes`. Produce deterministic results for empty, single-item and large inputs.

## Implementation steps

1. Test boundary cases and stability.
2. Implement the clustering algorithm.
3. Compare its output with the baseline and retain the Run parameters.

## Dependencies and boundary

Depends on m10-04 and the V2 attribution report contract (m12-24). This issue covers the clustering algorithm and its existing persistence interface.

## Verification

```sh
pnpm test:api -- tests/m12-04-clustering-upgrade
pnpm test:db
```

Verify the algorithm against the existing tables and API.

## Acceptance

Results are reproducible, and migrations preserve the database schema used by callers.

## Gates and CI

Run the algorithm gate, tests on both supported databases and fixture regression tests.

## Non-goals

Guarantees about diagnostic accuracy.
