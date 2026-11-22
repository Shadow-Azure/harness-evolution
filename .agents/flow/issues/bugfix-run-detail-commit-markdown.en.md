# Run detail step 6 renders the commit Markdown body as plain text, diverging from the V2 prototype

English | [中文](bugfix-run-detail-commit-markdown.md)

```yaml flow
kind: issue
id: bugfix-13
milestone: bugfix
depends:
  - m21-01
priority: P2
status: ready
scope:
  - apps/web/**
  - plans/ui-prototype-v2/**
  - plans/fullstack-design/**
  - tests/e2e/**
  - .agents/**
adr: []
github:
  number: 482
  url: https://github.com/Shadow-Azure/harness-evolution/issues/482
```

## Background

### Scenario

On 2026-11-22, inside the production Evolution → Run detail page at step 6 (Iteration), the user expanded an accepted round. The red-boxed area printed `finalCommit.message` verbatim: right after the `evolve(...)` subject, the card showed literal `## 问题`, `## 分析`, `## 改动`, `## 追溯`, `---`, and the `Harness-*` trailers; numbered items, long bad-case IDs, URLs, and paragraph breaks all collapsed into one continuous block. The `Harness-Evaluated-Commit` row and the 12-character hash above the block rendered normally; only the commit body was wrong.

Production evidence (the red box is the user's annotation of the checked position):

![Production step 6: the accepted commit Markdown body is shown as plain text](https://github.com/Shadow-Azure/harness-evolution/releases/download/run-detail-commit-markdown-evidence-20261122/prod-commit-raw.png)

Reproduction: production Evolution → history → any run with an accepted round → run detail → step 6 → expand an accepted round. The defect appears whenever `finalCommit.message` is the new multi-section Markdown produced by `build_accepted_message`; it is not tied to a specific run or bad case.

### Observations

- Markdown markers such as `##`, `---`, `-`, and `1.` are displayed literally instead of becoming headings, rules, lists, or links.
- Newlines in the commit body are collapsed: `## 问题`, `## 分析`, `## 改动`, and every `来源问题` line run together in one paragraph; long bad-case IDs and URLs then fill the width, making the block read like dumped logs.
- The whole block uses a monospace font and `word-break: break-all`; body, hash, and title have no visual hierarchy. The card grows with message length and pushes later rounds far below.
- This is display-only: the git commit, run branch, evaluation, and acceptance are correct, and copying the commit message still yields the full Markdown.

### V2 prototype comparison

The corresponding V2 prototype location `plans/ui-prototype-v2/harness-evolution.html#L5435` does not put the full commit body into the card. It uses `commit <short hash>　evolve(<target>): <title>` as the title line and then `cluster:`, `cases:`, and `phenomenon:` as a structured summary; `.commit .cline` only declares `white-space: pre-wrap` (`#L807`) and there is no Markdown parser. In other words, the prototype's treatment is a **bounded structured summary**, not a raw Markdown dump.

The accepted-round block in prototype step 6:

![V2 prototype step 6: the accepted commit uses a structured summary instead of the full Markdown body](https://github.com/Shadow-Azure/harness-evolution/releases/download/run-detail-commit-markdown-evidence-20261122/proto-commit-closeup-2x.png)

The prototype screenshot uses local demo data (`EV-20261109-01`, pushed to completion with the prototype's built-in `runprogress` demo parameter at a 1500×1000 viewport); its target differs from the production screenshot. The comparison is about the same page location (the accepted-round commit block at step 6) and information structure, not the same run or target.

The same prototype screen with context (evaluation comparison and following rounds stay near the first screen):

![V2 prototype step 6: the commit block is a compact card and later rounds remain visible](https://github.com/Shadow-Azure/harness-evolution/releases/download/run-detail-commit-markdown-evidence-20261122/proto-commit.png)

Production diverges from the prototype in two ways:

1. **Amount of information**: the prototype shows only the commit subject plus cluster facts; production shows the entire body (problem, analysis, change, trace, trailers) without any bound.
2. **Formatting**: the prototype at least keeps newlines for its three summary lines with `pre-wrap`; production's `.commit` has no `white-space`, so HTML collapses the body's newlines and the Markdown structure is completely lost.

### Root cause

1. **The backend already upgraded the commit message to full Markdown.** `build_accepted_message()` in `apps/api/app/service/evolution/git_candidate.py#L108-L147` joins `subject + _message_sections() + "---\n" + trailers`; `_message_sections()` (`#L753-L773`) always emits `## 问题`, `## 分析`, `## 改动`, `## 追溯` with `-` lists, URLs, and `Harness-*` trailers. `apps/api/app/service/evolution/stages.py#L1071-L1078` maps `round.commit_message` verbatim into `finalCommit.message`; the `StepFinalCommit.message` contract is a plain `string` with no "this is a short subject" constraint.
2. **The frontend still renders it as a one-line label.** `apps/web/src/pages/evolution/components/StepIterations.vue#L261-L264` interpolates `{{ round.finalCommit.message }}` as text and never invokes Markdown rendering. The `.commit` style (`#L469-L479`) only sets a monospace font and `word-break: break-all`, with no `white-space: pre-wrap`, so Markdown newlines collapse into spaces and `##` / `---` can only appear literally. Even adding `pre-wrap` would only preserve the raw text, not render Markdown.
3. **The design contract never defined how this message should be displayed.** The `finalCommit.message` example in `plans/fullstack-design/05-api-design.md#L422` is a single line, `evolve(deep-research@v2.0.0): 修复检索索引未校验导致的越界读取`; `plans/fullstack-design/08-frontend-implementation.md#L823` only says "show the amended commit" and does not state that the message is multi-section Markdown or how to render it. So the backend writes Markdown, the frontend reads a single line, and the prototype draws a structured summary; each is locally consistent, and together they produce the raw-text dump in the screenshot.
4. **Tests do not cover long Markdown.** `apps/web/src/pages/evolution/components/RunDetailConformance.test.ts#L427-L458` only asserts that `Harness-Evaluated-Commit` and the short hash appear; it has no fixture with `##` headings, lists, links, and newlines, and no collapsed/expanded behavior assertion. The regression therefore reaches production with green checks.

### Impact

- The core result of an accepted round at step 6 is unreadable: users cannot quickly see which cluster was accepted, why, which file changed, or which run it traces to, and must search a large monospace block for keywords.
- Long commit messages push later rounds and the bottom of the page off the first screen; at narrow viewports `break-all` also splits URLs and IDs in ways that are hard to copy.
- Data, evaluation, push, and git history are unaffected; this is a display-layer and design-contract divergence.

## Goals

- Restore a scannable structure to the accepted-round commit block: keep the 12-character hash and `Harness-Evaluated-Commit`, show the commit subject (the first line of `message`) in the title row, and stop showing `##`, `---`, and `-` as ordinary text.
- Render the commit body as Markdown: `##`/`###` become headings, `-` becomes lists, URLs become clickable links, and `---` becomes a rule. Collapse the body by default and expand on demand while preserving the Markdown structure.
- Match the V2 prototype's information architecture: the default view is close to the prototype's compact commit card (hash + subject + cluster facts), and the full message is an expandable supplement rather than the main view.
- Do not change the API, contracts, backend commit-message generation, or existing run data; old runs with a short message still display correctly.
- Lock "long Markdown is no longer plain text" and "collapsed by default, visible when expanded" with component tests and screenshot comparisons.

## Design authority

- [08 §10.3 Step6 iteration card](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#103-step6-迭代卡): the expanded order is source bad cases → patch → candidate → push → evaluation → final commit / rejection; accepted rounds must show the amended commit and `Harness-Evaluated-Commit`.
- [05 §3.6 iteration step contract](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/05-api-design.md#L422): `finalCommit = { hash, message }`; the current example is a one-line subject, so this issue must define the body shape.
- [V2 prototype step 6 accepted commit](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5435): `commit <hash>　evolve(...)` plus the `cluster:` / `cases:` / `phenomenon:` compact summary.
- [V2 prototype commit styles](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L804-L807): green commit card, highlighted hash, `cline` with `white-space: pre-wrap`, and no Markdown parser.
- [Existing safe Markdown renderer](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/src/utils/markdown.ts#L44-L64): `renderMarkdown()` uses markdown-it with `html: false`, forces `target="_blank"` and `rel="noopener noreferrer"` on links, and is already used by `ProblemDescription.vue` and `BadCaseList.vue`. This issue reuses that entry point instead of adding a second Markdown library.
- [m21-01 run detail re-layout](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/flow/issues/m21-run-detail-prototype-alignment.md): step 6 follows the V2 prototype's round-card order; this issue only fixes the commit display and does not revert its fields or hierarchy.

## Implementation

- `apps/web/src/pages/evolution/components/StepIterations.vue`:
  - Split `round.finalCommit.message` into subject and body: subject is the first line (the whole string when there is no newline); body is the remainder with leading/trailing blank lines removed. Show the subject on one line with ellipsis and keep the full text in `title`.
  - Keep the 12-character hash and subject in the title row; keep the `Harness-Evaluated-Commit` row unchanged.
  - Render the body with `renderMarkdown(commitBody, { images: false })` into a `.commit-message.markdown` container; `v-html` receives only that function's output, never concatenated unescaped user text.
  - Collapse by default: add an expanded set keyed by `round.roundId`; when the body is non-empty, show a "View full commit message" / "Collapse" toggle. Do not show the toggle when the body is empty or only contains the subject.
  - Styling: add scoped styles for `.commit-message` `h2`/`h3`, `p`, `ul`/`ol`, `li`, `a`, `code`/`pre`, and `hr` (reuse the existing markdown styles in `BadCaseList.vue` / `ProblemDescription.vue`); do not use `word-break: break-all` for the body, use `overflow-wrap: anywhere` instead; keep the hash unbroken; bound the body height and scrolling according to the prototype's compact-card density so a long message cannot grow the page without limit.
  - Leave the rejected branch unchanged: rejected rounds still say "candidate deleted, run branch unchanged" and do not show the commit hash.
- `plans/ui-prototype-v2/harness-evolution.html`:
  - Add a "Full commit message (Markdown)" collapsed example to the accepted-round commit card: by default show only the prototype's existing four-line summary; when expanded, show two or three Markdown sections (headings, list, link) with their rendered styles so the prototype can validate the "collapsed + expanded + Markdown" behavior.
  - If review decides the prototype should not gain an interaction, at least change the `cline` note to "summary only, full body not shown" and document production's extra expansion in the design doc; keep exactly one of these choices in the PR.
- `plans/fullstack-design/05-api-design.md` / `08-frontend-implementation.md`:
  - Change the `finalCommit.message` description to "full amended commit message (Markdown)"; add to 08 §10.3 that the UI shows the subject + cluster facts by default and renders the full body as Markdown after expansion, and that plain-text interpolation is forbidden.
  - If this issue keeps the prototype summary as the only view, document "full body not shown" and remove the expansion acceptance item instead.
- Tests:
  - `apps/web/src/pages/evolution/components/RunDetailConformance.test.ts`: add a `finalCommit.message` fixture containing `## 问题`, a list, a URL, `---`, and trailers; assert the default view contains no literal `##`/`---`, that heading, list, and link nodes exist, that the full body appears after the toggle and disappears after collapsing, and that the hash and `Harness-Evaluated-Commit` remain.
  - If the existing E2E can seed an accepted round, add a step-6 expansion case: long Markdown produces no horizontal scroll and the page still scrolls to later rounds.

## Implementation steps

1. Add subject/body splitting, expansion state, and `renderMarkdown` rendering to `StepIterations.vue`, changing only the accepted branch; run the focused component test to confirm short messages do not regress.
2. Add `.commit-message` Markdown styles and long-text wrapping/scrolling constraints; confirm the commit hash, `Harness-Evaluated-Commit`, and the rejected branch are unaffected.
3. Update the `RunDetailConformance.test.ts` fixture and assertions; add E2E if needed.
4. Update the V2 prototype commit card and the 05/08 design docs; keep the prototype/design descriptions consistent.
5. Capture Before / After screenshots on a local production-shaped page with synthetic fixtures (same viewport, theme, and accepted round) plus the V2 prototype block; label Before with the current baseline commit.
6. Run focused unit tests, typecheck, lint, E2E, `verify:flow`, and document gates; include screenshots, commands, and limitations in the PR description.

## Dependencies and boundary

- Depends on: m21-01 (run detail already follows the V2 prototype; this issue only fixes the step-6 commit display and does not revert its card order, fields, or tabs).
- Boundary: run-detail display components under `apps/web`, their component tests/E2E, the V2 prototype, and the 05/08 design docs; do not change the API, `packages/contracts`, database, git commit-message generation, evaluation, or acceptance flow.
- Do not rewrite historical commits or migrate old `finalCommit.message` values; a one-line old message still displays as the subject.
- Do not write production run IDs, Session content, production screenshots, or credentials into the repository; screenshot evidence lives in the Release / PR description, while the repository keeps only reproducible fixtures and tests.

## Verification

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/components/RunDetailConformance.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m10-06"
pnpm verify:flow
pnpm lint:docs
```

- The component fixture uses a multi-line message containing `## 问题`, a `-` list, `https://example.com`, `---`, and `Harness-Evaluated-Commit`: the default `.commit` text contains no literal `##` or `---`; `.commit-message h2`, `li`, and `a[href]` exist; clicking "View full commit message" reveals the body and "Collapse" hides it; a short one-line message shows no toggle.
- On the production-shaped page at 1500×900 with the light theme, an accepted round shows only hash + subject + summary by default; after expansion, headings, lists, and links render as Markdown; the page has no horizontal scroll and can still reach later rounds.
- Against the V2 prototype at the same viewport, the default view's information density matches the prototype commit card, and the expanded Markdown headings/lists/links match the design doc.
- Existing assertions for `Harness-Evaluated-Commit`, the 12-character hash, candidate ref/commit, evaluation comparison, and the rejected explanation do not regress; `verify:flow` and `lint:docs` pass.

## Acceptance

- The production step-6 accepted round no longer shows literal `## 问题`, `## 分析`, `---`, or other Markdown markers, and newlines are no longer collapsed into one paragraph.
- The default view matches the V2 prototype: hash + commit subject + cluster summary, with the body collapsed by default and a discoverable "View full commit message" entry; the expanded body renders as Markdown with clickable links.
- A long commit message neither breaks the card nor creates horizontal scroll; later rounds and the bottom of the page remain reachable.
- An old run's single-line `finalCommit.message` displays as the subject without an empty body or a redundant toggle; the rejected-round behavior is unchanged.
- No API/contract/backend changes; component tests cover long Markdown and collapse/expand, and E2E covers the step-6 regression (if the existing fixture cannot seed an accepted round, cover it in component tests and state the E2E limitation in the PR).
- The PR includes same-scenario, same-viewport, same-theme Before / After screenshots (Before labelled with the baseline commit) and the V2 prototype block; no production screenshot is committed to the repository.
- Final acceptance by the requester: this issue is not closed until the requester confirms the whole flow has no remaining problem for now.

## Gates and CI

- Unit tests and coverage: `pnpm test:web` (at least `RunDetailConformance.test.ts`).
- Type and lint: `pnpm typecheck:web`, `pnpm lint:web`.
- E2E: `pnpm test:e2e -- "m10-06"`, plus a new step-6 case for this issue if needed.
- Flow: `pnpm verify:flow`; commits and the PR title include `(#<this issue number>)`.
- Docs: run `pnpm lint:docs` after changing the V2 prototype or the 05/08 design docs; run `pnpm record:i18n` and the document gates for any paired permanent-doc changes.
- Deliver for human review after CI is green; a person merges this PR.

## Non-goals

- Do not change the backend commit-message structure, section copy, trailers, or git amend / push behavior.
- Do not change the API, `packages/contracts`, database fields, or historical run data; do not backfill bodies for old runs.
- Do not add a new Markdown library, enable raw HTML, or render images from the commit message; keep using the existing `renderMarkdown()` security configuration.
- Do not re-layout the other step-6 sections (source bad cases, patch, candidate, push, evaluation) or change steps 1–5/7 or the execution log.
- Do not put the full commit message in the default view, and do not treat `pre-wrap` as "rendering complete".
- Do not write production run IDs, Session content, production screenshots, or credentials into the repository.
