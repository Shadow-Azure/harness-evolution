# Agent Note: Pure Agent-tree Layout Boundary

Status: implemented

English | [中文](2026-10-26-agent-tree-layout.md)

## Problem

The Session tree API already returns flat Agents, trigger events, and explicit bad-case anchors, while the prototype geometry depends on React Flow, DOM measurement, and JSONL line differences. Moving that logic directly into a Vue component would make layout depend on browser timing, duplicate backend semantics, and couple problem-card rendering to the graph core.

## Decision

`components/agent-tree/layout.ts` consumes only `SessionTree` and emits framework-independent nodes, orthogonal channels, branch segments, and bad-case anchor descriptors. Layout copies input Agents and events before edge reconciliation, and duplicate Agent or main identities fail closed instead of rendering a partial duplicate graph. Trigger `×N` gaps use assistant `messageOffset`; proportional bar width has a JSONL-line lower bound, and injected text measurement uses the real 11px label font. Wide trigger chains expand the node so source handles and pills retain the same final coordinates. An unknown ordinary parent trigger degrades to main with a synthesized agent event instead of borrowing a Workflow. Nearby sibling triggers share a trunk only when their trigger X positions are within 24px, and more than eight children collapse. Collapse branches also enter the finding-side collision set.

m3-02 computes anchors for self-skill, self-agent, discovery, and fallback cases without creating finding nodes. The minimal `AgentTree.vue` is a thin Vue Flow renderer over the layout output; the hidden, development-only `/agent-tree-demo` route defaults to the four-node `demo-nested` core tree, while `?variant=large` exists only for real collapse/trunk interaction checks. In m3-03, the production Session overview independently loads `/api/sessions/{sid}/tree` and mounts `AgentTree.vue` asynchronously only after data arrives. Tree loading, empty, failure, and retry states do not replace the list or summary; node selection updates Agent focus, and a fully expanded branch can be collapsed from the panel. Vue Flow outer node/edge keyboard focus is disabled so each native Agent button is the sole Tab stop and no node has duplicate focus. After the node set or container size changes, the canvas waits for DOM measurement and runs `fitView` again, keeping every node visible when a large graph expands on a narrow screen; cleanup cancels pending frames and timers and disconnects the ResizeObserver. Vue Flow remains in its own dynamic chunk and never enters the `/sessions` first-load closure, and parent edges use a closed arrow marker.

`/sessions/:sid?agent=&evidence=` is the only source of the active Agent and evidence position. The parser treats Vue Router's path parameter as already decoded and rejects duplicate/control/oversized IDs and evidence without an Agent; the tree response remains the authority for Agent existence and event-index range. Session routes strip error-only `case/tab` values, while the error route parses them for m4. Accepted non-canonical queries are rewritten with `router.replace`, and a later valid History restore clears stale inline notices. Evidence highlighting applies only to the selected Agent, so equal event indices never highlight other nodes. A deep-linked descendant automatically expands its collapsed ancestors, and locating waits until the target node appears. Invalid tree state is removed with an inline notice rather than falling back to another Session; auto-selection occurs only on `/sessions`, never by replacing an explicit filtered Session. Node selection clears stale evidence and writes canonical URL state. Both 1408px and 390px verify refresh restoration, node visibility, and no horizontal overflow; a real Chrome fixture verifies folded-target expansion. The formal `/sessions/:sid/errors?case=&tab=` parser is ready for m4, but its cross-Session 409 is not inferred locally: m4-02 supplies the bad-case ownership response to the resolver seam.

## Alternatives considered

- Measure and lay out inside the component: deterministic tests become dependent on DOM and font timing.
- Keep JSONL line deltas for `×N`: it conflicts with the normalized assistant-message contract.
- Render problem cards in m3-02: this pulls m4 visual and interaction ownership into the graph core.

## Consequences

Layout results are stable under input permutations without a browser, and a development route covers the real canvas. Components only render geometry, resize the viewport, and emit collapse events, while malformed input surfaces as stable diagnostics. Real problem cards consume anchor descriptors in m4 later; production Session integration remains m3-03. Real-browser suites run serially because each owns an API, Vite server, SQLite file, and Chrome process; the shared browser launcher also cleans its child process and profile after a failed startup and retries once so a transient CI failure cannot leave the test step hanging.

Deep links survive refresh, history navigation, and new-window navigation without serializing private message content. m4 must validate case ownership against the backend before rendering its error page; until then, the pure resolver seam exposes the mismatch contract without fabricating a response.
