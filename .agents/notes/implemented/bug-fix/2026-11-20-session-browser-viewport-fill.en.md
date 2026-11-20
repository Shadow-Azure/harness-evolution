# Agent Note: Fill the Session page viewport at low content

Status: implemented

English | [中文](2026-11-20-session-browser-viewport-fill.md)

## Problem

The production "Session error view" page reported a large page-background band below the content for a Session with only 1 user turn, 1 message, 0 tool calls, 0 sub-agents, and 1 bad case; the V2 prototype at the same viewport has no such band ([GitHub #415](https://github.com/Shadow-Azure/harness-evolution/issues/415)).

The current main Session shell already fixes its height to `100vh - header`, the document does not scroll, and the problem list scrolls inside the right column, so the full-page scroll and 300–550px band in the production capture do not reproduce with a synthetic Session on current main. Two remaining gaps do reproduce: `.overview` fills the right column but its content ends at natural height above the bottom when it is shorter than the viewport; and the execution flow is an async chunk that renders nothing until it arrives, so the right column first collapses to a header-only panel with no placeholder above the problem list. The first appears on taller viewports or when the flow is absent; the second appears briefly on every first paint.

## Decision

The Session page owns the viewport height: `.session-browser` uses `100dvh` minus the shell header (with a `100vh` fallback) and keeps `min-height: 0` and `overflow: hidden`. Document scrolling stays disabled; the left `.sidebar` and right `.overview` remain the only scroll containers.

The right `.overview` stays a block scroll container; `.overview-content` becomes a column flex container that fills the available height with `min-height: 100%`, and the trailing problem list fills the remaining height while the content is shorter than the viewport. When content is taller, the list keeps its natural height and `.overview` scrolls. The fill applies to containers, not to problem-card bodies.

The async execution-flow chunk gets loading and failure components, both keeping a prototype-scale full-height placeholder (720px desktop, 420px narrow); the data loading, failure, and no-data branches of the flow itself use the same placeholder. The right column therefore never ends early while the chunk is pending, after a request failure, or when no flow exists. At ≤860px the page keeps its single-column natural height without the fixed viewport.

## Alternatives considered

- **Disable `body` scrolling globally**: this hides document scrolling on every page, including overview and evolution pages that need it; rejected in favor of scoping the fix to the Session shell.
- **Stretch the problem list or card bodies**: this leaves a large blank inside a single card and departs from the prototype's content-height cards; rejected in favor of filling only the list container.
- **Shrink the flow canvas to fit one screen**: this changes the default graph size for multi-agent Sessions and is a content reflow; rejected, so the flow keeps its own height and the right column scrolls when content is taller.
- **Only redeploy production without a code change**: the production build matches current main's Session shell code, but the reproducible async-chunk collapse and low-content fill gaps remain; rejected.

## Consequences

- Low-content Session pages no longer show page-background blank at the bottom of the right column; at 1500×1100 the problem list fills the remaining height and the last content sits about 18px above the viewport bottom.
- While the flow chunk is pending on first paint, a full-height skeleton is shown instead of blank; a failed chunk shows "execution flow view failed to load" instead of silently collapsing.
- The flow placeholder is 720px, so a low-content first paint is briefly taller than the final layout and the page contracts once the chunk arrives; this is the cost of keeping prototype-scale space.
- The full-page scroll and 300–550px band in the production capture do not reproduce on current main; this change fixes the reproducible right-column collapse and low-content fill. The production build and hash still need confirmation on the deployment side.
- The parent `.workspace-main` still uses `100vh`; on dynamic-toolbar browsers wider than 860px the Session page and the shell can differ by one background strip. Unifying them needs a shell-level change, which was left out of scope.
- Mobile behavior is unchanged; problem-list data, filters, and card structure are unchanged.
