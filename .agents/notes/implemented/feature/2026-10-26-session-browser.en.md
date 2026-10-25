# Agent Note: Session browser prototype delivery

Status: implemented

English | [中文](2026-10-26-session-browser.md)

## Problem

The session query API now returns real root sessions and whole-tree statistics, while the frontend still shows a placeholder. The prototype requires operators to triage by status, failure density, and problem density directly in a 360px sidebar, then inspect a statistics overview on the right. Frontend re-sorting or aggregation would fork the URL, API truth, and prototype visuals.

## Decision

The session browser uses backend order as the only list order. Search, status, and sort values are written to URL query parameters, and the selected root session is encoded as `/sessions/:sessionId`. With data at `/sessions`, the first item is selected automatically; after filtering, a selection that no longer exists is replaced by the first current result. List and overview use independent requests. The overview follows the detail response and only falls back to the current list item while detail is in flight; either side can fail without blocking the other. Problem counts use `stats.badCases`; both density bars use backend per-100-message statistics and clamp at a full scale of three per hundred messages.

The Session route is a full-width workspace directly below the 56px top bar: a 360px `--bg-panel` sidebar and a fluid right pane without a rounded outer card. Status and sort each have a labeled row. The Agent graph placeholder uses the prototype 720px panel scale below the nine-item StatStrip, and the error-detail CTA sits in the overview header. Listbox/option semantics apply only when options are present, using roving tabindex, arrow and Home/End navigation, `aria-selected`, and readable status text; route changes invalidate a pending search timer so history navigation cannot be overwritten. The placeholder does not request `/tree`; until the m4 page exists, the error-detail CTA stays disabled to avoid a fake link.

## Alternatives considered

- Fetch `/tree` in the frontend and aggregate locally: this duplicates backend semantics and blocks the list on a future graph capability.
- Keep selection only in component memory: refresh and browser history would lose it, violating prototype acceptance.
- Hard-code the problem count to zero: external `bad_cases` is already read-only truth, so zero would mislead triage.

## Consequences

List and overview share one contract while retaining independent states, and URLs are directly shareable and restorable. Below 860px the layout becomes single-column while all four cards remain reachable in the same workspace. The Agent graph and error details remain for later issues; the current page fabricates neither graphs nor problem details.
