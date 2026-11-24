# Agent Note: Step 5/6 source cases use the bad-case short title

Status: implemented

English | [中文](2026-11-24-iteration-source-case-title-projection.md)

## Problem

Run-detail step 6 "iteration" and step 5 "clusters and severity" rendered the attribution summary as the source bad-case title: `_cluster_cases()` filled `StepClusterCase.title`, taking `attribution_by_case[bad_case_id].probe_description` on the V2 branch and `probe_row.probe_description` on the legacy branch. In production one run had 20 rows of 422–1541 characters (795 on average), stretching every row into several paragraphs of prose and pushing object_name, type, trigger point, and reported time to the right; a reviewer could not check which cases that iteration covered. By design `bad_cases.title` is the short title required on report (47 characters in the production sample) and `reason` is the description body, so the two text levels are already distinct in the data; the seven-step projection simply read the wrong field (GitHub #570). A precedent for the same "short field exists in the data path but the projection drops it" class of fix is [2026-11-20-run-detail-session-short-title.md](2026-11-20-run-detail-session-short-title.en.md).

## Decision

- Read titles in one batch: `BadCaseRepository.titles_by_ids()` issues one read-only `bad_case_id IN (...)` SELECT and returns a case-id to short-title map, keeping the external-table error boundary through `@read_only_guard("bad_cases")`; an empty input returns an empty dictionary.
- Assemble at the facts layer: `_facts()` picks the run's case source by whether candidates exist (candidates' `bad_case_id` when present, otherwise the probe rows'), dedupes while preserving order, calls `titles_by_ids()` once, and stores the map in `_RunFacts.case_titles`. The two branches of `_cluster_cases()` only look the map up and never query per row.
- Both projections take the short title: the V2 branch uses `facts.case_titles.get(candidate.bad_case_id) or candidate.bad_case_id`, the legacy branch `facts.case_titles.get(row.bad_case_id) or row.bad_case_id`. A missing title is a tolerated branch that falls back to the stable `bad_case_id`, never to `probe_description`.
- Step 4 keeps its boundary: `StepAttributionRow.description` still carries the attribution summary from `probe_description`; `_v2_attribution_rows()` and `_legacy_attribution_rows()` are unchanged, so the long prose appears only in that column.
- No contract or frontend change: `StepClusterCase` keeps its fields, no OpenAPI or generated types and no `apps/web` change; historical runs need no re-prepare because titles are read live.

## Alternatives considered

- **Call `get_case()` once per case**: rejected. A run has dozens of cases, so a per-case loop turns assembly into N extra database queries, and the seven-step projection rebuilds facts on every request.
- **Add a `detail` or summary field to `StepClusterCase`**: rejected. That is a contract and frontend change beyond this issue's delivery boundary; the title column reads the wrong field, it is not missing a field.
- **Truncate `probe_description` in the frontend or clamp with `line-clamp`**: rejected. The issue lists this as a non-goal; truncation still shows attribution prose in the title column and copies presentation rules into the client.
- **Fall back to `probe_description` when a title is missing**: rejected. That is exactly the mixing this issue removes; `bad_case_id` is less readable but semantically correct and traceable, and it cannot push long prose back into the title column.
- **Cache titles at process level outside `_RunFacts`**: rejected. Titles belong to external tables and can change at any time, so a cache adds invalidation problems; one batch read per request is already cheap.

## Consequences

- The step 5/6 source tables show the source bad-case short title again, while step 4's "symptom/description" column keeps the full attribution summary; the two text levels now sit in their proper places in the projection.
- `_RunFacts` gains `case_titles` as a required dependency and `EvolutionStageService` gains a `BadCaseRepository` constructor argument; production wiring reuses one repository instance in `main.py`, and the `tests/evolution` and placeholder-eval suites pass the dependency explicitly.
- Every seven-step request adds one `IN` query; both the candidate and probe paths issue it once, independent of case count.
- Historical runs need no re-prepare; `bad_cases.title` values that are themselves abnormally long are out of scope for this issue.
