# Agent Note: V2 prototype UI readability and interaction fixes

Status: implemented

English | [中文](2026-11-11-ui-prototype-v2-ui-polish.md)

## Problem

Real-browser review of the V2 prototype exposed several visible defects that distort evaluation: four top-level entries wrap inside words at 1408px; the family tree treats a normal wheel as zoom, so readers trying to scroll down shrink the graph to an unreadable scale; `--text-faint` is used for chart ticks and table metadata at roughly 2.6:1 contrast; the Session shell still subtracts 100px after the sub-tabs were hidden, leaving a 44px band at the bottom; long session IDs push the detail actions to a second line; and the source-total column plus evolution-target pager do not align with card edges.

## Decision

Fix the same `plans/ui-prototype-v2/harness-evolution.html` with the smallest diff: make top-level entries non-shrinking and single-line, hiding subtitles below 1340px; disable wheel zoom and allow page scrolling on both React Flow instances, raising `minZoom` to 0.5; change `--text-faint` to `#66707c` and enlarge ticks and totals; set the Session shell to `calc(100vh - 56px)`, let the detail header's first column shrink, and ellipsize long IDs; widen the source-total column to 120px; and make the evolution-target side card a column flex container with a bottom-pinned pager. Before/after evidence lives under `plans/ui-prototype-v2/_ui-review/`.

## Alternatives considered

- Edit production `apps/web` directly: it mixes prototype review with product implementation, and this issue only covers prototype assets.
- Hide subtitles only below 1100px: the 1408px wrap remains unsolved.
- Keep wheel zoom and move the legend into a fixed overlay: the gesture conflict remains and users still zoom by accident.
- Only darken the color: contrast improves, but 9px dates on a dense weekly axis remain hard to read.

## Consequences

The prototype drifts further from production frontend styling; future alignment work should treat this note and its screenshots as the reference. Review screenshots add repository weight but make each turn auditable. The 1340px threshold and 0.5 minimum zoom are empirical; re-measure if real data lengthens labels.
