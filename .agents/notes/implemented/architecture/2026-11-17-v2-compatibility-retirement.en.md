# Agent Note: V2 compatibility retirement conditions and documentation close-out

Status: implemented

English | [中文](2026-11-17-v2-compatibility-retirement.md)

## Problem

V2 has made workspaces, credential ingest, overview, multi-attribution, and seven-step runs the default path, but the resident docs still describe V1: `docs/architecture.en.md` says single-organization, read-only attribution, and six steps, while `plans/fullstack-design/README.md` still records the architecture sync as debt. V1 read endpoints, workspace-less routes, legacy runs, and nullable columns remain live without a shared version trigger or mechanical deletion conditions. Waiting longer would make "how long is compatibility" a matter of memory, and deletion could miss frontend dead code, contract types, tests, and docs.

## Decision

- The deletion trigger is V3, the first major version after V2; the V2 compatibility window keeps every V1 surface and only records conditions, without deleting endpoints, routes, fields, or migrations early.
- Add [compatibility.en.md](../../../../docs/compatibility.en.md) as the sole home for compatibility surfaces, the trigger version, and the mechanical checklist; `docs/architecture.en.md` and `docs/development.en.md` only link to it.
- Rewrite the resident docs from the implementation: workspaces and roles, credential ingest, workspace Sessions and overview, multi-attribution, the four-step wizard, seven-step runs and the lane DAG, evidence grades/execution outcome/knowledge triggers become current facts, with V1 compatibility listed as a boundary.
- Sync the design Notes: the "retired in m11-06" wording in [workspace-shell-routing](2026-11-15-workspace-shell-routing.en.md), [attribution-read-api](../feature/2026-11-17-attribution-read-api.en.md), and [multi-attribution-error-detail](../feature/2026-11-17-multi-attribution-error-detail.en.md) now points to the V3 checklist.
- Sync the `plans/fullstack-design` entry: the README "to be synced" debt becomes synced, and 15 §7's compatibility step points to compatibility.
- This PR changes no code, contract, migration, or test, and leaves compatibility and user-visible behavior unchanged.

## Alternatives considered

- Delete V1 endpoints and routes now: this would break old bookmarks, external ingest clients, and compatibility pages, and violates the issue's non-goals; rejected.
- Keep compatibility indefinitely: there would be no mechanical exit condition and the architecture would carry two paths forever; rejected.
- Put the checklist into architecture: it would exceed the word budget and make architecture hold step-by-step content; rejected in favor of "current state → architecture, steps → development/compatibility".
- Tighten the nullable columns to NOT NULL immediately: existing V1 rows may lack a probe or cache key, making the migration unsafe; rejected, backfill first.
- Change only plans and not the resident docs: plans are not the resident source of truth, so readers would still see V1; rejected.

## Consequences

- V2 keeps the two-path test and contract cost; V3 clears it in one pass through the compatibility checklist.
- Before V3 deletion, confirm zero calls, no old links, no legacy-run reads, and backfilled nullable columns; otherwise compatibility stays.
- A compatibility-surface change must update compatibility, the architecture link, and the owning Note together; one fact, one home.
- This change adds no user-visible behavior; verification relies on docs/flow/contract gates.
