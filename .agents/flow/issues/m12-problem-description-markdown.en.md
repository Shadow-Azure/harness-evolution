# Render problem descriptions as Markdown

English | [中文](m12-problem-description-markdown.md)

```yaml flow
kind: issue
id: m12-17
milestone: m12
depends: []
priority: P1
status: in-progress
scope:
  - apps/web/**
  - tests/e2e/**
  - fixtures/**
  - plans/**
  - docs/**
  - .agents/notes/**
  - .agents/flow/**
adr:
  - ../../notes/implemented/feature/2026-11-18-problem-description-markdown.md
github:
  number: 363
  url: https://github.com/Shadow-Azure/harness-evolution/issues/363
```

## Background

On 2026-11-18 a user reported on the production "Session 错误查看" page that the problem-description block (the red box in the original screenshot) is one wall of plain text, with no grouping or line breaks for long failure lists. The `[SWE-bench] astropy__astropy-13398 · unresolved` bad case in the screenshot squeezes four F2P failures and six P2P regressions into one paragraph, so it can only be read character by character, and test names have no inline-code boundary.

`bad_case_description` is free text. The external report/analysis side already organizes it as "status + failure group + case list", but HE renders it as plain text; HTML collapses line breaks and Markdown syntax has no effect.

### Current path

- Ingest: an external system writes `bad_cases.bad_case_description`; HE maps it verbatim to `BadCase.reason` in `apps/api/app/db/crud/bad_cases.py`; [06 §4.1](../../../plans/fullstack-design/06-database-design.md) says the description body is "displayed directly".
- Display: `ProblemDescription.vue` interpolates `{{ problem.reason }}` directly in `.problem-detail` (lines 117–122).
- Existing capability: the attribution "reasoning" is rendered through `renderMarkdown` in `apps/web/src/utils/markdown.ts` (markdown-it, `html:false`, `breaks:true`, `linkify:true`, hardened external links) and has `.markdown` styling (`AttributionReport.vue` lines 287–292 and 596+). The problem description does not use this path.
- Result: line breaks, lists, code fragments, emphasis, and links all collapse into one flat paragraph; longer descriptions become unreadable.

### Evidence

**Before / after (same case, 1440×1400 viewport, light theme, 2× DPR)**

[![Problem description Markdown before/after](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/problem-description-compare.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/problem-description-compare.png)

Originals: [before](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/problem-description-before.png) · [after](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/problem-description-after.png)

Downloadable updated prototype: [prototype-problem-description-markdown.html](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/prototype-problem-description-markdown.html). Open it, log in with any demo account, go to "Session 错误查看", and select the `SWE-bench astropy-13398` session.

Note: the before capture uses the current single-line plain text (the same shape as the reported SWE-bench failure list); the after capture uses the Markdown form of the same case, showing lists, inline code, and grouping. Both were captured from the V2 prototype before/after the change, not from production code.

## Goals

- Render the problem description as Markdown, with clear hierarchy for lists, paragraphs, inline code, emphasis, links, and code blocks.
- Preserve single line breaks (`breaks:true`) so legacy multi-line plain text becomes readable immediately.
- Render safely: disable raw HTML, harden external links, and add no script execution surface.
- Do not regress plain text without Markdown syntax: it remains a normal paragraph with all text preserved.
- Update the V2 prototype and keep before/after evidence so the implementation follows the same information architecture.

## Design authority

- [05 §3.4 bad case detail](../../../plans/fullstack-design/05-api-design.md): `reason` DTO semantics and field mapping.
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md): `bad_case_description` is the description body, currently "displayed directly".
- [08 §7 error detail page](../../../plans/fullstack-design/08-frontend-implementation.md): information hierarchy of the error detail, problem-description tab, and the Markdown boundary of attribution text.
- Existing implementation: `apps/web/src/utils/markdown.ts` and `AttributionReport.vue` on the same page.
- [V2 design §8 error detail](../../../plans/ui-prototype-v2/design-v2.md): the one-bad-case × many-attributions layout and the problem-description tab.
- [V2 prototype](../../../plans/ui-prototype-v2/harness-evolution.html): `FindingDescription` and `.ed-detail.markdown` as the visual baseline.

## Implementation

- **Frontend rendering**: `ProblemDescription.vue` adds `reasonHtml = computed(() => renderMarkdown(problem.reason))`; the body becomes `<div class="problem-detail markdown" data-testid="problem-detail" v-html="reasonHtml" />`, with the same eslint comment as `AttributionReport`.
- **Security boundary**: reuse `renderMarkdown`; add no Markdown dependency; `html:false` escapes raw HTML; `link_open` hardens external links; no syntax highlighting.
- **Typography**: align `.markdown` with the current description size/line height (12.5px / 1.7); add spacing for `p`, `ul/ol`, `li`, `code`, `pre`; inline code uses a `--mono` + `--bg-inset` chip; long test names use `overflow-wrap:anywhere`; code blocks scroll horizontally; emphasis and links use existing tokens.
- **Empty/plain text**: empty descriptions render nothing; plain text without Markdown syntax keeps equivalent text content, and single line breaks become `<br>`.
- **Prototype**: `FindingDescription` in `plans/ui-prototype-v2/harness-evolution.html` follows the same contract and keeps the SWE-bench demo case; production matches the prototype.
- **Tests**: add assertions for Markdown lists, inline code, hard breaks, raw HTML, and link attributes in `ProblemDescription.test.ts`; lock `breaks` and escaping in `markdown.test.ts`; keep the existing error-detail E2E green and add a Markdown fixture assertion if needed.
- **Docs and Note**: update the display contract in `05`, `06`, `08`; add an Agent Note recording why Markdown, why reuse the existing renderer, and why no raw HTML or syntax highlighting.

## Implementation steps

1. Write the failing `ProblemDescription.test.ts` cases first and confirm the current plain-text implementation cannot render lists/inline code.
2. Wire `renderMarkdown` into `ProblemDescription.vue` and add `.problem-detail.markdown` scoped `:deep()` typography.
3. Run the focused unit tests, typecheck, and lint; add `markdown.test.ts` assertions for line breaks/escaping.
4. Update `plans/fullstack-design/05`, `06`, `08` and the V2 design doc; add the Agent Note and re-record the bilingual pair.
5. Smoke the real frontend: inject a Markdown description into seeded data, capture screenshots, compare with the V2 prototype at the same viewport, and fix differences.
6. Open the PR, wait for CI, review per `docs/review.md`; handle findings, then re-run smoke and CI.

## Dependencies and boundary

- Dependencies: none. This issue changes no API, database column, contract type, or permission; `bad_case_description` stays free text and only display changes.
- The data-side format convention is a parallel dependency: existing plain text remains safe (line breaks start working), but grouped lists require the upstream side to emit Markdown; record that in `06` and `05`.
- Delivery boundary: `ProblemDescription.vue`, its tests/styles, the prototype, design docs, and the Note; do not change the split between plain-text `AttributionReport.reason` and Markdown `reasoning`.

## Verification

```sh
pnpm --filter @harness/web test -- src/pages/errors/components/ProblemDescription.test.ts src/utils/markdown.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern "m4 error detail"
```

- Expected: the description renders `<ul>/<ol>`, `<code>`, `<strong>`; line breaks are preserved; raw HTML produces no nodes; external links carry `target="_blank"` and `rel="noopener noreferrer"`; plain-text descriptions keep the same text content.
- Manual: open the SWE-bench demo case in the V2 prototype and confirm the F2P/P2P grouped list and inline code; compare with the before screenshot above.
- Smoke: run the real frontend with a temporary data directory, inject the same Markdown description, capture screenshots, and compare with the prototype; do not commit temporary data or screenshots.

## Acceptance

- Markdown lists, inline code, emphasis, links, and code blocks render as expected in the problem description.
- Single line breaks are visible; multi-line plain text no longer collapses into one paragraph.
- Raw HTML does not execute; external links are hardened; plain-text descriptions do not regress.
- The V2 prototype contains the same demo case, and the before/after screenshots match the description.
- The PR contains refreshed before/after screenshots, real-frontend smoke screenshots compared with the prototype, and component/utility tests.

## Gates and CI

- `pnpm --filter @harness/web test -- src/pages/errors/components/ProblemDescription.test.ts src/utils/markdown.test.ts`
- `pnpm typecheck:web`, `pnpm lint:web`
- `pnpm test:e2e -- --pattern "m4 error detail"`
- `pnpm verify:flow`, `pnpm test:gates`, `pnpm lint:docs`
- PR title and commit messages contain `(#363)`; review per `docs/review.md`.

## Non-goals

- Add no Markdown rendering library and change no `renderMarkdown` security configuration.
- Do not auto-rewrite historical plain text into Markdown or guess formats.
- Do not change bad-case ingest contract fields, database columns, or API shape; only clarify the display convention.
- Do not change the error-detail information architecture, colors, or other blocks; do not change the plain-text rendering of attribution `reason`.
