# Agent Note: External Issue Read Models

Status: implemented

English | [中文](2026-10-26-external-read-models.md)

## Problem

`bad_cases`, `bad_case_analysis`, and `probe_reports` are written by external systems. Reading the tables directly or assembling attribution row by row spreads upstream field drift, invalid probe links, and N+1 queries into page failures while blurring this service's read-only boundary.

## Decision

`db/crud/bad_cases.py` batch-SELECTs the three external tables from one read session, and the service alone derives the five display states. Runtime migrations maintain only service-owned tables; external tables are created by their owner or an explicit development-fixture bootstrap. `analyzed_issue` requires a probe from the same session, while `analyzed_nonissue` and `unanalyzed` must not link one. Invalid links degrade to `unanalyzed` with stable, sanitized warning codes. Probe reverse sources accept only `analyzed_issue` links whose case and probe share the session. `analysis_result` is validated against the issue `summary` and non-issue `reason/reasoning[]` shapes; status and links remain while malformed snapshots are cleared. Missing identity fields skip the row with a lookup diagnosis; malformed presentation fields retain safe placeholders. Database timestamps are normalized to Asia/Shanghai at the outbound boundary. The five states are query-time projections with no extra database enum or derived column.

## Alternatives considered

Continuing to assemble issues inside the session service would blur tree and external-problem boundaries. A derived database column would duplicate external truth. Returning 500 on drift would let one bad row break a page. Development fixtures need self-contained test/demo data, so an explicit bootstrap switch creates external tables; application runtime migrations and the repository never write them.

## Consequences

m4-02 must consume this service and add HTTP error mapping. Drift degrades instead of crashing, but warnings must remain observable. m4-01 provides neither problem HTTP APIs nor an error-detail page. Production deployments must provision external schemas before starting the API.
