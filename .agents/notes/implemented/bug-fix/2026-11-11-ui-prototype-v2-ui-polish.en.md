# Agent Note: V2 prototype UI readability and interaction fixes

Status: implemented

English | [中文](2026-11-11-ui-prototype-v2-ui-polish.md)

## Problem

Real-browser review of the V2 prototype exposed several visible defects that distort evaluation: four top-level entries wrap inside words at 1408px; the family tree treats a normal wheel as zoom, so readers trying to scroll down shrink the graph to an unreadable scale; `--text-faint` is used for chart ticks and table metadata at roughly 2.6:1 contrast; the Session shell still subtracts 100px after the sub-tabs were hidden, leaving a 44px band at the bottom; long session IDs push the detail actions to a second line; and the source-total column plus evolution-target pager do not align with card edges.

The third turn found further state and content mismatches: rejected iterations in a completed run still showed a positive delta, the final-evaluation subtitle kept the literal "M" placeholder, and a rising issue-reproduction rate was colored as a gain; the add-member dialog granted Space Admin by default; the workspace-management list left a large blank area; and the last Session stat label wrapped at 1280px.

## Decision

Fix the same `plans/ui-prototype-v2/harness-evolution.html` with the smallest diff: make top-level entries non-shrinking and single-line, hiding subtitles below 1400px; disable wheel zoom and allow page scrolling on both React Flow instances, raising `minZoom` to 0.5; change `--text-faint` to `#66707c` and enlarge ticks and totals; set the Session shell to `calc(100vh - 56px)`, let the detail header's first column shrink, and ellipsize long IDs; widen the source-total column to 120px; and make the evolution-target side card a column flex container with a bottom-pinned pager. Before/after evidence lives under `plans/ui-prototype-v2/_ui-review/`.

The second turn fixes interaction state: page and workspace are written to the URL; menus close on outside click, Escape, or page change; the family-tree canvas adapts to short viewports and the legend moves into normal flow; the error-detail execution flow compresses on short viewports so the case detail is visible; switching workspace closes the old workspace's error detail and refreshes the new workspace Sessions; and the timeline only renders for the Session with real data, showing a correctly titled empty state otherwise.

The third turn makes rejected candidates score below current, uses the real iteration count in the final-evaluation subtitle, and adds a `lowerBetter` direction to `evDelta`; it defaults the add-member role to Member, lowers the admin content minimum height to 340px, labels the run-card percentage as total progress, and keeps Session stat labels on one line with tighter cell padding.

## Alternatives considered

- Edit production `apps/web` directly: it mixes prototype review with product implementation, and this issue only covers prototype assets.
- Hide subtitles only below 1100px: the 1408px wrap remains unsolved.
- Keep wheel zoom and move the legend into a fixed overlay: the gesture conflict remains and users still zoom by accident.
- Only darken the color: contrast improves, but 9px dates on a dense weekly axis remain hard to read.

## Consequences

The prototype drifts further from production frontend styling; future alignment work should treat this note and its screenshots as the reference. Review screenshots add repository weight but make each turn auditable. The 1400px threshold, 0.5 minimum zoom, and canvas height clamps are empirical; re-measure if real data lengthens labels or adds nodes. URLs use `replaceState`, so refresh restores the current page and workspace; browser back still leaves the prototype, and full history semantics would need `pushState` plus `popstate` replay.
