# Agent Note: Pure Agent-tree Layout Boundary

Status: implemented

English | [中文](2026-10-26-agent-tree-layout.md)

## Problem

The Session tree API already returns flat Agents, trigger events, and explicit bad-case anchors, while the prototype geometry depends on React Flow, DOM measurement, and JSONL line differences. Moving that logic directly into a Vue component would make layout depend on browser timing, duplicate backend semantics, and couple problem-card rendering to the graph core.

## Decision

`components/agent-tree/layout.ts` consumes only `SessionTree` and emits framework-independent nodes, orthogonal channels, branch segments, and bad-case anchor descriptors. Layout copies input Agents and events before edge reconciliation, and duplicate Agent or main identities fail closed instead of rendering a partial duplicate graph. Trigger `×N` gaps use assistant `messageOffset`; proportional bar width has a JSONL-line lower bound, and injected text measurement uses the real 11px label font. Wide trigger chains expand the node so source handles and pills retain the same final coordinates. An unknown ordinary parent trigger degrades to main with a synthesized agent event instead of borrowing a Workflow. Nearby sibling triggers share a trunk only when their trigger X positions are within 24px, and more than eight children collapse. Collapse branches also enter the finding-side collision set.

m3-02 computes anchors for self-skill, self-agent, discovery, and fallback cases without creating finding nodes. The minimal `AgentTree.vue` is a thin Vue Flow renderer over the layout output; the hidden, development-only `/agent-tree-demo` route defaults to the four-node `demo-nested` core tree, while `?variant=large` exists only for real collapse/trunk interaction checks. Production Session wiring belongs to m3-03. Vue Flow remains in its own dynamic chunk, and parent edges use a closed arrow marker.

## Alternatives considered

- Measure and lay out inside the component: deterministic tests become dependent on DOM and font timing.
- Keep JSONL line deltas for `×N`: it conflicts with the normalized assistant-message contract.
- Render problem cards in m3-02: this pulls m4 visual and interaction ownership into the graph core.

## Consequences

Layout results are stable under input permutations without a browser, and a development route covers the real canvas. Components only render geometry and emit collapse events, while malformed input surfaces as stable diagnostics. Real problem cards consume anchor descriptors in m4 later; production Session integration remains m3-03.
