# Agent Note: Synchronous launch validation and the 202 admission contract

Status: implemented

[English](2026-10-27-launch-wizard-admission.md) | English

## Problem

The m5-05 launch wizard must realize 05 §4.9/§4.10 and 07 §5.3 without inventing a second design: the probe preview needs real hit statistics for wizard step 2, starting a run must reject synchronously when the object is unconfigured, the window is inverted, or zero probes match, while actual filtering and clustering stay asynchronous. The boundary: a `202` from `POST /runs` only means "admitted for preparation"; the prepare orchestration itself belongs to m5-06.

## Decision

- The hit semantics are unified as "analyzed_issue reports for the object pair": `badCases` counts by `bad_cases.object_*`, `probes`/`items` come only from analysis-linked probes; unanalyzed reports only increment `unanalyzed` with a waiting-for-external-attribution hint, and zero hits always yield `409 NO_PROBES_MATCHED`.
- `POST /api/evolution/probes/query`, `POST /api/evolution/runs`, and `POST /api/evolution/cluster-previews` share `ProbeQueryRequest` and one validation path; at admission the target snapshot (repo_url/sub_dir/default_ref), window, models, engine_key (default = mode), and eval config are persisted with the run row so launch parameters stay traceable.
- A successful launch only inserts one `status=preparing` `evolution_runs` row and enqueues `evolution_prepare`; this slice registers no prepare handler, so runs stay preparing and cluster_only runs can only ever surface a preparing state until m5-06 lands.
- The wizard implements the two prototype steps: only configured and enabled objects are listed, "next" runs the preview, step 2 renders statistics, the distribution bar, and the probe table with the cluster-only and full-run exits; both jump to preparing-state landing pages at `/evolution/runs/:rid` and `/evolution/cluster/:rid`, while the full detail page remains m5-07 scope.

## Alternatives considered

- A GET preview with query strings: conditions include model arrays and must be reusable as the launch body; the POST body matches 05 §4.9. Rejected.
- Implementing the cluster_only prepare handler (filter → simple_cluster → persist clusters → terminal state) in this slice: it requires run status transitions plus step APIs that belong to m5-06. Rejected.
- Polling until clusters exist before closing the wizard: the 202 semantics say do not wait; detail/preview polling belongs to m5-07 and 08 §11. Rejected.

## Consequences

- `NO_PROBES_MATCHED` and `TARGET_NOT_CONFIGURED` become shared error codes; wizard step 1 must render the 409 as "adjust the condition", not a failure page.
- Until a prepare handler is wired, no run ever leaves preparing and the run list keeps showing "preparing" — an expected placeholder, not a defect.
- The landing pages read one run from the list endpoint; the dedicated `GET /runs/{rid}` endpoint and SSE subscription must replace this when m5-07 closes 05 §4.10.
