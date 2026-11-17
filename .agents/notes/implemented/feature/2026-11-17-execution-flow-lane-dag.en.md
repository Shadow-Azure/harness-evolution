# Agent Note: Lane DAG as the default execution flow

Status: implemented

English | [中文](2026-11-17-execution-flow-lane-dag.md)

## Problem

V1 drew the whole Agent tree as a Vue Flow node graph: concurrency was only implied by nodes sitting side by side, depth by indentation, `>8` child agents collapsed into a summary node, and selecting a bad case filtered out the other branches. The V2 prototype instead requires a default view where one agent invocation is one lane, bar edges are log-line intervals, horizontal overlap across lanes is concurrency, and `A1/A1.1` expresses depth, while the structural tree remains available as a toggle. Layering those geometric constraints onto the node graph makes layout, selection, and performance pull against one another.

## Decision

- Add `agent-tree/AgentFlow.vue` as the single entry point: the `lane` mode is the default and a button switches to `tree`; both views share `activeBadCaseId`, `activeAgentId`, and the deep link, so toggling never resets the selection.
- `agent-tree/lane/laneModel.ts` is pure: tree → lane/bar/marker/concurrency-band/spawn group. The main lane is `A1`; children are numbered `A1.1`, `A1.1.1`, and so on. Siblings are ordered by trigger line, and a child without a trigger event falls back to the end of its parent lane.
- The horizontal axis uses log lines only: a trigger event occupies its own line, and every line between two triggers becomes a `×N no trigger` bar, so the main lane covers 0–100 contiguously and never overlaps itself. `messageOffset` stays reserved for the structural tree's message gaps; the two N meanings are never mixed. A child lane starts at its parent trigger and scales its width by its own log-line count, capped at 42%.
- Every lane is rendered: there is no `>8` folding or summary row. Browsing instead uses a fixed small viewport (`clamp(360px, 48vh, 520px)`) with wheel zoom, drag pan, fit, and 1:1 reset. `lane/viewport.ts` keeps zoom/pan/fit as pure functions, and the component only owns the transform.
- Selecting a bad case only thickens its locator line and highlights the matching bar; no lane or branch is filtered. A BC marker resolves its trigger line from `anchor.agentId + anchor.eventIndex`; when it lands in a no-trigger interval it still marks that line and names the nearest triggers.
- The structural tree moves wholesale under `agent-tree/tree/` and keeps reusing `layout.ts`'s `chainOf/buildGraph`; `types.ts` keeps the shared tree types and adds the lane model types. Vue Flow therefore becomes a toggle view instead of owning the default execution flow.

## Alternatives considered

- **Keep Vue Flow as the default execution flow**: a node graph cannot express concurrency as horizontal overlap, and `>8` folding conflicts with the stress session; rejected, Vue Flow serves only the structural tree.
- **Keep `>8` folding with summary nodes**: folding loses lane identity, so the 57th child cannot be located; rejected in favor of viewport zoom/pan.
- **Filter other branches while a case is selected**: the prototype explicitly requires every concurrent branch to remain visible with only the target highlighted; rejected, since filtering makes "absent" look like "not selected".
- **Use real timestamps as the horizontal axis**: normalized data has no reliable `triggered_at`, and inventing a duration would make bar length meaningless as evidence; rejected, the log-line logical order is the axis for now and unknown timestamps use hatched bars.
- **Render every bar as real DOM with a virtualized window**: 56 lanes with a few bars each are acceptable in a fixed viewport, while virtualization adds positioning and E2E complexity; rejected, render all bars and scale with transform.

## Consequences

- Large sessions fit the whole canvas at a tiny scale, so readers must zoom in for detail; that is the cost of showing every lane.
- Without real timestamps, bar length means log-line proportion only, and both the footnote and tooltips say "not real elapsed time".
- Child positions derive from the parent lane interval; paths and indentation stay correct beyond three nested levels, but readability depends on zoom.
- The structural tree and lane DAG keep separate layouts while sharing types and selection; future execution-flow work must account for both views.
- Web unit tests cover lane paths, intervals, concurrency, markers, viewport, and 61-lane expansion; E2E covers the default DAG, zoom/pan, the structural-tree toggle, error-detail selection, and the 61-lane stress session.
