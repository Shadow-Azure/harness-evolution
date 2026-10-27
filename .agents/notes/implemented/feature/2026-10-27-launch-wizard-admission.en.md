# Agent Note: Synchronous launch validation and the 202 admission contract

Status: implemented

English | [中文](2026-10-27-launch-wizard-admission.md)

## Problem

The m5-05 launch wizard must realize 05 §4.9/§4.10 and 07 §5.3 without inventing a second design: the probe preview needs real hit statistics for wizard step 2, starting a run must reject synchronously when the object is unconfigured, the window is inverted, or zero probes match, while actual filtering and clustering stay asynchronous. The boundary: a `202` from `POST /runs` only means "admitted for preparation"; the prepare orchestration itself belongs to the later engine slices (m5-09–m5-11).

## Decision

- Hit semantics start from `probe_reports` and never match the reported object `bad_cases.object_*`: probes are selected by `probe_object @ object_version` (plus `probe_type`), then the linked bad case is read through `bad_case_analysis.probe_id` and the session through `probe_reports.session_id`; when the reported object and the root-cause object diverge, only the root-cause object matches.
- Statistics and pagination follow the probe scope: `sessions` counts distinct matched probe sessions, `badCases` counts distinct cases linked from matched probes, `analyzed` counts the distinct `analyzed_issue` cases among them, and `probes`/`usedProbes` count distinct probes; `byAttributeType` reads `probe_reports.attribute_type`, while `unanalyzed`/`nonIssue` keep their fields but are always 0 because unanalyzed and non-issue reports never enter `items` or the zero-hit 409 check; `from/to` filters on the probe session start and `models[]` matches any agent model in that session tree.
- `POST /api/evolution/probes/query`, `POST /api/evolution/runs`, and `POST /api/evolution/cluster-previews` share `ProbeQueryRequest` and one normalization path: all three resolve the target configuration first, preview and launch both fall back to `default_ref` when no version is requested, and a missing or disabled target always yields `409 TARGET_NOT_CONFIGURED`; at admission the target snapshot (repo_url/sub_dir/default_ref), window, models, engine_key (default = mode), and the redacted eval config are persisted with the run row, with credential-like eval fields going through the same redaction as job payloads (`sanitize_job_payload`), so no plaintext secret is stored.
- A successful launch only inserts one `status=preparing` `evolution_runs` row and enqueues `evolution_prepare`; this slice registers an explicit placeholder handler that completes the job successfully with a placeholder result/log marker while the run stays `preparing`; the real prepare orchestration (workspace clone, ref validation, filtering, clustering) is wired by the later engine slices (m5-09–m5-11).
- `engineKey` is not validated against an engine registry in this slice and is persisted as supplied; `422 ENGINE_INVALID` (unregistered engineKey or invalid eval) is provided by the engine slices' engine registry.
- The wizard implements the two prototype steps: only configured and enabled objects are listed, "next" runs the preview, step 2 renders statistics, the distribution bar, and the probe table with the cluster-only and full-run exits; both jump to preparing-state landing pages at `/evolution/runs/:rid` and `/evolution/cluster/:rid`, while the full detail page remains m5-07 scope.

## Alternatives considered

- A GET preview with query strings: conditions include model arrays and must be reusable as the launch body; the POST body matches 05 §4.9. Rejected.
- Implementing the cluster_only prepare handler (filter → simple_cluster → persist clusters → terminal state) in this slice: it requires run status transitions plus step APIs that belong to the later engine slices. Rejected.
- Polling until clusters exist before closing the wizard: the 202 semantics say do not wait; detail/preview polling belongs to m5-07 and 08 §11. Rejected.

## Consequences

- Hit counts, distribution, and items are decoupled from the reported object: choosing a target shows exactly that root-cause object's probes, so historical data where the reported object and root-cause object diverge cannot cross over; unanalyzed and non-issue reports always render as 0 in the wizard and never affect the zero-hit check.
- Preview and launch share condition normalization and error semantics: omitting `targetVersion` resolves `defaultRef` in both, and preview also returns 409 for a missing or disabled target; `NO_PROBES_MATCHED` and `TARGET_NOT_CONFIGURED` become shared error codes that wizard step 1 must render as "adjust the condition", not a failure page.
- A `202` no longer leaves an inevitably failed `evolution_prepare` job: the job completes successfully with a placeholder result/log marker while the run stays `preparing` for the engine slices' real prepare; until the engine is wired, the run list keeps showing "preparing".
- The landing pages read one run from the list endpoint; the dedicated `GET /runs/{rid}` endpoint and SSE subscription must replace this when m5-07 closes 05 §4.10.
