# Problem Description Markdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Render `BadCase.reason` as safe Markdown in the error-detail problem description, matching the V2 prototype and preserving the existing plain-text behavior.

**Architecture:** Reuse the existing `renderMarkdown` helper (markdown-it with `html:false`, `breaks:true`, `linkify:true`, hardened external links) inside `ProblemDescription.vue`, add scoped `:deep()` typography for the resulting `p/ul/ol/li/code/pre/strong/a` nodes, and lock the behavior with component/utility tests. No API, DB, or contract change; the data-side Markdown convention is documented only.

**Tech Stack:** Vue 3 `<script setup>`, markdown-it 14, Vitest + jsdom, CDP-driven E2E, headless Chrome.

**Spec:** [GitHub #363](https://github.com/Shadow-Azure/harness-evolution/issues/363), [flow issue m12-17](../../../.agents/flow/issues/m12-problem-description-markdown.md), [plans/fullstack-design/05 §3.4](../../../plans/fullstack-design/05-api-design.md), [06 §4.1](../../../plans/fullstack-design/06-database-design.md), [08 §7](../../../plans/fullstack-design/08-frontend-implementation.md), [V2 design §8](../../../plans/ui-prototype-v2/design-v2.md), [V2 prototype](../../../plans/ui-prototype-v2/harness-evolution.html).

## Global Constraints

- No new Markdown dependency; keep `renderMarkdown`'s `html:false`, `breaks:true`, `linkify:true`, and link hardening exactly as-is.
- Keep the problem description at 12.5px / 1.7 and preserve the existing card spacing; do not restyle the error-detail shell.
- `BadCase.reason` becomes Markdown; `AttributionReport.reason` stays plain text and `reasoning` stays Markdown.
- Historical plain text must not regress; single line breaks become `<br>` and raw HTML is escaped.
- Flow issue m12-17 is mapped to #363; commit messages and PR title carry `(#363)`.
- Screenshots and smoke JSON are evidence only, not committed to the repository; design docs and the Agent Note are committed.
- Chinese/English pairs must be re-recorded after edits (`pnpm record:i18n -- <pair>`).

## Review Focus

- A reason containing raw HTML must not create DOM nodes or execute anything; `renderMarkdown` must be the only path.
- A reason containing a bare URL must get `target="_blank"` and `rel="noopener noreferrer"`, not a relative link.
- A plain-text reason with no Markdown syntax must keep the same visible text (existing component and E2E assertions).
- A reason with hard line breaks must produce `<br>`, not collapse into one paragraph.
- Long inline-code test names must wrap inside the card, not force horizontal overflow.

---

### Task 1: Establish the flow/issue mapping and base

**Files:**
- Modify: `.agents/flow/milestones/m12-milestone.md`, `.agents/flow/milestones/m12-milestone.en.md`
- Create: `.agents/flow/issues/m12-problem-description-markdown.{md,en.md,i18n.yaml}`
- Modify: `.agents/notes/implemented/feature/2026-11-18-problem-description-markdown.{md,en.md,i18n.yaml}`

- [x] Reopen local M12 (`status: active`), add m12-17 with `github.number: 363`, `status: in-progress`, and scope covering `apps/web/**`, tests, fixtures, plans, docs, notes, and flow.
- [x] Record the issue, milestone, and Note pairs with `pnpm record:i18n`.
- [x] Run `pnpm verify:flow` and confirm it is green before code changes.

### Task 2: RED — component proves the description does not render Markdown

**Files:**
- Modify: `apps/web/src/pages/errors/components/ProblemDescription.test.ts`

- [x] **Step 1: Add a Markdown reason to a mounted component**

Use `badCaseFixture` with:
```ts
reason: [
  "**result_status** = `unresolved`",
  "",
  "**F2P 失败**",
  "- `test_cirs_its_topo`",
  "- `test_its_straight_overhead`",
  "",
  "line one",
  "line two",
  "[source](https://example.com)",
].join("\n")
```

Assert the `.problem-detail` subtree contains `<ul>`, `<li>`, `<code>test_cirs_its_topo</code>`, `<strong>result_status</strong>`, `<br>` between the two plain lines, and an `<a>` with `href="https://example.com"`, `target="_blank"`, `rel="noopener noreferrer"`.

- [x] **Step 2: Add a raw-HTML case**

Assert `reason: '<img src=x onerror="alert(1)"><script>alert(2)</script>'` produces no `<img>` and no `<script>` nodes, while the escaped text is still present.

- [x] **Step 3: Run the focused test and verify it fails**

Run:
```sh
pnpm --filter @harness/web test -- src/pages/errors/components/ProblemDescription.test.ts
```
Expected: FAIL because the current component interpolates plain text and has no list/code/link nodes.

### Task 3: GREEN — render Markdown and style it

**Files:**
- Modify: `apps/web/src/pages/errors/components/ProblemDescription.vue`

- [x] **Step 1: Add the computed HTML**

Import `renderMarkdown` from `../../../utils/markdown`; add:
```ts
const reasonHtml = computed(() => renderMarkdown(props.problem.reason));
```

- [x] **Step 2: Replace the text interpolation**

```vue
<!-- eslint-disable vue/no-v-html -- MarkdownIt raw HTML is disabled and links are hardened. -->
<div
  class="problem-detail markdown"
  data-testid="problem-detail"
  v-html="reasonHtml"
/>
<!-- eslint-enable vue/no-v-html -->
```

- [x] **Step 3: Add scoped typography**

In the existing `<style scoped>`, keep `.problem-detail` and add `:deep()` rules for `p`, `p:last-child`, `ul/ol`, `li`, `code`, `pre`, `pre code`, `strong`, and `a`. Use `--mono`, `--bg-inset`, `--border`, `--text`, `--blue`; inline code gets a compact chip, long names get `overflow-wrap:anywhere`, and code blocks scroll horizontally.

- [x] **Step 4: Run the focused test and verify it passes**

Run:
```sh
pnpm --filter @harness/web test -- src/pages/errors/components/ProblemDescription.test.ts
```
Expected: PASS, including the existing plain-text/order assertions.

### Task 4: Lock the renderer contract

**Files:**
- Modify: `apps/web/src/utils/markdown.test.ts`

- [x] **Step 1: Add hard-break and plain-text cases**

Assert `renderMarkdown("line one\nline two")` contains `<br>`; assert a plain Chinese sentence without Markdown syntax has no `<p>`-breaking surprises and escapes `<`/`>`.

- [x] **Step 2: Run the utility tests**

```sh
pnpm --filter @harness/web test -- src/utils/markdown.test.ts
```
Expected: PASS.

### Task 5: Docs and evidence

**Files:**
- Modify: `plans/fullstack-design/05-api-design.md`, `06-database-design.md`, `08-frontend-implementation.md`
- Modify: `plans/ui-prototype-v2/design-v2.md` if the prototype section needs the new detail
- Evidence: release `issue-markdown-prototype-evidence-20261118` (compare/before/after PNGs + prototype HTML)

- [x] **Step 1: Update the display contract**

In `05 §3.4`, state that `BadCase.reason` is Markdown-rendered (`html:false`, hardened links). In `06 §4.1`, change “直接展示” to “按 Markdown 渲染，原始 HTML 不渲染”. In `08 §7`, add a note under the problem-description tab and keep the attribution `reason` plain-text / `reasoning` Markdown split explicit.

- [x] **Step 2: Keep evidence out of the repo**

Use the existing release URLs and PR description; do not commit screenshots or smoke JSON. The modified prototype HTML is committed at `plans/ui-prototype-v2/harness-evolution.html`.

### Task 6: Full verification

- [x] **Step 1: Focused checks**

```sh
pnpm --filter @harness/web test -- src/pages/errors/components/ProblemDescription.test.ts src/utils/markdown.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm verify:flow
pnpm test:gates
```

- [x] **Step 2: Error-detail E2E**

```sh
pnpm test:e2e -- --pattern "m4 error detail"
```
Expected: PASS; plain-text fixture reasons still compare equal.

### Task 7: Real-frontend smoke and prototype comparison

**Files:**
- Evidence only: `.ticket-assets/smoke/*` (do not commit)

- [x] **Step 1: Start an isolated app**

Seed fixtures into a temporary data directory, update one case's `bad_case_description` to the Markdown sample, start the API and Vite (see the smoke script), and log in as admin through the API.

- [x] **Step 2: Capture**

Use CDP to set the refresh cookie, navigate to `/workspaces/ws-default/sessions/<sid>/errors?case=<id>&tab=desc`, wait for `[data-testid='problem-detail']`, and capture the `.detail-panel` at 1440×1400 CSS / 2× DPR.

- [x] **Step 3: Compare**

Compose the real-app capture with the V2 prototype’s `.err-detail` capture at the same viewport; check list indentation, code chip, line height, and card width. Fix any material difference before the PR.

- [x] **Step 4: Report**

Render the smoke JSON with `.agents/skills/computer-use-smoke-reporting/scripts/render-smoke-report.mjs`; link the report and comparison images from the PR description (not committed).

### Task 8: PR, CI, review, and handoff

- [x] **Step 1: Commit and push** with `(#363)` in every commit title.
- [x] **Step 2: Open the PR** with milestone M12, the before/after and smoke evidence, design/UI comparison, verification commands, and the material data-format limitation.
- [x] **Step 3: Poll CI with a script** until every check is terminal; fix failures and repeat.
- [x] **Step 4: Run the `pr-review` skill**, write `plans/2026-11-18-pr<N>-review.md`, assess findings, and use `pr-review-fix` for accepted findings.
- [x] **Step 5: Re-run smoke and CI** after fixes.
- [ ] **Step 6: Report ready** with the PR URL; a person merges the PR per the deployment policy, then the flow close PR can mark m12-17 done and close #363.
