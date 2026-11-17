# Agent Note: Folded multi-attribution error detail

Status: implemented

English | [中文](2026-11-17-multi-attribution-error-detail.md)

## Problem

m11-01 made a bad case's attributions readable per object/revision, but error detail still used the V1 single-card sidebar plus one probe analysis: several conclusions for one case could not be visible together, refresh restored only `case` and `tab` without `at`, and "non-target" shared the old unanalyzed copy. An empty-attribution case could only start evolution by leaving for the evolution page. Pulling every attribution into one request would bypass server paging, while keeping `/analysis` and `/probes/{id}` would re-elevate the probe to a product concept and contradict the m11-01 contract.

## Decision

- Replace the sidebar with `CaseGroup` + `AttributionItem`: the parent row shows `BC<no>`, the short bad case id, title, self/discovery, object_name, and an attribution count; children page two per request (`pageSize=2`). Expanded state and page number stay local; URL selection drives and auto-expands the case; filter chips only filter the list, never the expanded state or the detail pane.
- Deep links are `case`, `tab`, and `at`. `at` is only valid on the attribution tab and requires `case`. Resolution prefers `at`, then the prototype-compatible `obj` object name, then the first item. Validation stays in `router/deepLink.ts`; the page consumes only normalized state and does not rewrite the URL to the resolved first item.
- The detail navigator needs `N / total` and previous/next, so selecting a case also reads one `pageSize=50` attribution list (bounded extra pages by `total`) for `at` resolution and stepping. The sidebar keeps server paging at two rows per page; the two use separate cache keys so "current page" and "full set" never share one meaning.
- `AttributionReport` renders the 08 §7.3 order: conclusion banner, object/revision, source run, time, cache, confidence and policy, trigger comparison, reason, Markdown reasoning with fixed evidence gaps, and the conclusion boundary. `reason` is plain text; `reasoning` uses the existing safe Markdown pipeline; a non-target conclusion shows no category chip.
- With no attribution, show "尚未归因", explain that evolution generates it, and offer "start evolution from this case" only to `space_admin`/`global_admin`. The wizard is an overlay on this page prefilled with `focusCaseId`; opening it does not leave error detail, while a successful launch moves to the run detail.
- Every attribution query key starts with `["ws", workspaceId, "case", badCaseId, ...]`; switching workspaces resets expansion, pages, filters, and the wizard so stale detail cannot leak across spaces.
- `ProblemDescription` replaces the single-probe report link and five-state chip with "已生成 N 条归因 · X 可归因 / Y 非该对象 →". The legacy `analysis` stays on lists and compatibility APIs; error detail no longer calls `/analysis` or `/probes`.

## Alternatives considered

- **Read every attribution into the sidebar and paginate in the client**: simpler, but violates the server `pageSize=2` contract and inflates first paint as cases grow; rejected. Only the detail navigator asks for the full set.
- **Treat `at` as a direct detail read and 404 when it is not on the current page**: refreshing an `at` from another page would falsely report it missing; rejected, resolve through the full set first.
- **Keep reusing `BadCaseAnalysis` and `ProbeReport`**: collapses an object-level attribution set back into one probe and cannot express non-target, cache, or trigger comparison; rejected, error detail uses the m11-01 attribution contract.
- **Send the empty-attribution call to action to the evolution page**: the prototype launches in place, and leaving loses the current case and filter context; rejected, mount the wizard here.
- **Auto-select the first case by default**: the prototype does, but the current page defaults to "all bad cases" plus an empty detail and changing that breaks deep links and keyboard paths; rejected, keep the empty state and let the URL choose.
- **Build `at` deep links by string concatenation in components**: bypasses the `obj` compatibility and invalid-value checks; rejected, use `badCaseDeepLink` and `parseSessionDeepLink`.

## Consequences

- Selecting a case costs one extra 50-row attribution read; it is bounded by `total`, only loops beyond 50 rows, and only while error detail is open.
- The sidebar page follows the selected `at` and switches to the page that contains it. The page number is driven only by the selection and is not written to the URL; refresh and copied links still follow `at`.
- Conclusions are still written only by evolution; error detail is read-only and never performs manual attribution or mutates the bad case.
- Execution-flow layout and keeping all concurrent branches when a case is selected remain m11-07's work; this page still filters the flow to the selected case.
- V1 `/analysis`, `/probes/{id}`, and `BadCase.analysis` remain for lists and compatibility pages; the V3 retirement must also remove the old error-detail reads and frontend dead code, following [compatibility.en.md](../../../../docs/compatibility.en.md).
