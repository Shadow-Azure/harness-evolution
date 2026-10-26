# Agent Note: Backend Fact Boundary for Evolution Run Lists

Status: implemented

English | [中文](2026-10-27-evolution-run-list.md)

## Problem

The evolution home must show active and historical runs with stage, progress, iteration, acceptance, final-evaluation, and error facts. If the browser regroups, reorders, or derives percentages from a cursor, the database snapshot, API, and interface can disagree about the same run. The API design's RunCard example also omits a creator while the Issue requires one.

## Decision

`GET /api/evolution/runs` reads runs, creators, actual cluster counts, accepted-iteration counts, and finals in one batched snapshot. It returns `running` and `history` groups ordered by `created_at DESC, id DESC`; `preparing`, `running`, and `blocked` are active, while terminal states are historical. The backend owns `progress.total`, `percent`, `stageLabel`, `doneRounds`, `accepted`, and normalized stats. The frontend maps display values without recalculating them. RunCard adds nullable `createdBy` beyond the API-design fields and places it in the prototype's upper-right time slot without adding a visual row.

## Alternatives considered

Client-side state grouping would turn prototype ordering into an implementation detail; per-run cluster, iteration, and final queries would create N+1 reads and potentially inconsistent snapshots; Python `round` would use bankers rounding at .5 and differ from prototype rounding-up behavior; omitting the Issue's creator requirement would leave an acceptance gap. All were rejected.

## Consequences

The run list depends on one repository aggregation and one stable API projection, and the query must remain covered on SQLite and MySQL. A deleted creator yields a null display name while run snapshots remain visible. Later SSE work may invalidate the run-list query but must not treat pushed payloads as durable facts.
