# Agent Note: External Issue Read Models

Status: implemented

English | [中文](2026-10-26-external-read-models.md)

## Problem

`bad_cases`, `bad_case_analysis`, and `probe_reports` are written by external systems. Reading the tables directly or assembling attribution row by row spreads upstream field drift, invalid probe links, and N+1 queries into page failures while blurring this service's read-only boundary.

## Decision

`db/crud/bad_cases.py` batch-SELECTs the three external tables and the service alone derives the five display states. `analyzed_issue` requires a probe from the same session, while `analyzed_nonissue` and `unanalyzed` must not link one. Invalid links degrade to `unanalyzed` with stable, sanitized warning codes. Probe reverse sources accept only `analyzed_issue` links whose case and probe share the session. `analysis_result` is validated against the issue `summary` and non-issue `reason/reasoning[]` shapes; status and links remain while malformed snapshots are cleared. Missing identity fields skip the row with a lookup diagnosis; malformed presentation fields retain safe placeholders. The five states are query-time projections with no extra database enum or derived column.

## Alternatives considered

Continuing to assemble issues inside the session service would blur tree and external-problem boundaries. A derived database column would duplicate external truth. Returning 500 on drift would let one bad row break a page. Development fixture writes remain a self-contained test/demo exception; the runtime repository exposes no write methods.

## Consequences

m4-02 must consume this service and add HTTP error mapping. Drift degrades instead of crashing, but warnings must remain observable. m4-01 provides neither problem HTTP APIs nor an error-detail page.
