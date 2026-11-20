# Agent Note: Re-layout the evolution run detail after the V2 prototype

Status: implemented

English | [中文](2026-11-19-run-detail-prototype-alignment.md)

## Problem

The production "Evolution → Run detail" page turns workspace information into a separate card between "Goal and input" and "Flow progress", pushing progress behind a third card. "Goal and input" shows a "Models (multi-select)" field that neither the prototype nor the design document has, and lacks the prototype's "Workspace", "Attributed / non-target", and policy/cache source badges. The header shows creator · time, while design document 08 §10.1 requires "title + status + workspace badge". The distribution title counts "concluded attributions" instead of the prototype's "attribution conclusion distribution of potential bad cases". The prototype itself lacks the "Execution log" tab and the "preparing" state, which design document 08 §10.2 / §10.4 requires, so the same page cannot be accepted against the prototype. See GitHub #403 for the comparison evidence.

## Decision

- The detail page becomes a single column: header (title + status + workspace badge) → goal and input → flow progress → current step output. The standalone "Workspace" card is removed; run branch, base, repository, subdirectory, push and eval state, and local paths move into a collapsible area at the bottom of "Goal and input", and the branch name stays copyable.
- "Goal and input" follows the prototype field set: target / version / window / workspace, associated Sessions, bad cases in window, potential bad cases, attributed / non-target. "Models (multi-select)" is removed. The distribution title becomes "Attribution conclusion distribution of potential bad cases (N)" and the legend adds "non-target" and "new this run", using the potential count as the denominator.
- No API contract change: policy and cache switches come from the reached range step's `condition.policy` / `condition.cacheEnabled`; non-target, reused and fresh are counted per row from the attribution step's `rows` (`category` null means non-target, `source` distinguishes cached / fresh; "new this run" counts only fresh attributed rows, matching the prototype). Until attribution finishes those three show `—` and a "not attributed" remainder completes the distribution bar. Both step queries share query keys with the selected step, so the same key is never fetched twice, and the log tab does not issue them.
- Keep the "Seven steps / Execution log" tabs and the "preparing" state, and close the prototype gap in the same change: the prototype gains tabs, a log panel, a workspace badge, the workspace collapsible area, and a preparing example run. Design document 08 §10.1 gains the distribution wording and workspace collapse, and §10.4 states the tab shape.

## Alternatives considered

- **Keep the standalone workspace card and move it after progress**: rejected. The design assigns workspace information to the info panel, and a full-width card still leaves the page hierarchy wrong.
- **Add `nonTarget` / `sessionsTotal` to `EvolutionRunStats`**: rejected. The issue forbids API contract changes; the attribution step already exposes exact `nonTarget` / `reused` / `fresh`, and the range step exposes policy and cache switches.
- **Derive non-target as `potential - attributed`**: rejected. While preparing or attributing, that difference includes unanalyzed rows and would mislabel them as non-target; read the attribution summary once the step is reached.
- **Drop the production tabs and preparing state to match the old prototype**: rejected. Design document 08 §10.2 / §10.4 requires the execution log tab and the preparing state; the right move is to complete the prototype, not remove production behavior.
- **Keep "Models (multi-select)" and add it to the prototype and design document**: rejected. Model filtering is not part of the prototype or design information architecture and the detail page has no per-model interaction; keeping it would leave two field sets on one page.

## Consequences

- The detail page reads two extra steps on first load (range and attribution, enabled by step state; preparing reads only range and unreached steps are not requested). They share the cache with the selected step, so switching to those steps does not refetch.
- "Associated Sessions" still shows `associated / version-unresolved` because the contract does not expose the total Session count in the window; the prototype's `associated / total` uses sample data and production does not invent the total.
- "Models (multi-select)" disappears from the detail page; the run snapshot and API field stay for other consumers.
- The V2 prototype gains the log tab, a preparing example, the workspace badge, and the workspace collapsible area; design document, prototype, and production now agree on fields and order.
- Component tests (goal-and-input fields, workspace location, policy/cache badges, distribution copy, tabs and preparing state) and E2E (header, card order, workspace not standalone) cover the change; before / after screenshots go in the PR description.
