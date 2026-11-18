# Agent Note: Render problem descriptions as Markdown

Status: implemented

English | [中文](2026-11-18-problem-description-markdown.md)

## Problem

`BadCase.reason` (`bad_cases.bad_case_description`) is the body of the error detail's "问题描述" tab. It comes from external reports or trace analysis and is often "status + failure group + case list": F2P failures, P2P regressions, and individual test names. `ProblemDescription.vue` currently interpolates `{{ problem.reason }}` directly; the browser collapses line breaks into spaces, so lists, inline code, and emphasis do not render. A SWE-bench unresolved case becomes three continuous lines of text, and failed test names must be scanned character by character.

The attribution "reasoning" on the same page already has a safe Markdown path: `utils/markdown.ts` renders with markdown-it (`html:false`, `breaks:true`, `linkify:true`) and `link_open` adds `target="_blank"` and `rel="noopener noreferrer"`; `AttributionReport.vue` consumes it with `v-html` and `.markdown` typography. The problem description did not reuse that path, even though both are external free text with the same security boundary.

CSS `white-space: pre-wrap` alone could restore line breaks, but not lists, inline code, or emphasis. Having the frontend detect "is this a failure list" and auto-format would turn the display layer into a guesser, and would still miss code blocks and links.

## Decision

- `ProblemDescription.vue` adds `reasonHtml = computed(() => renderMarkdown(problem.reason))` and writes it with `v-html` into `problem-detail markdown`, with the same eslint comment as `AttributionReport`. Reuse the existing renderer; add no dependency.
- Scoped CSS uses `:deep()` for `.problem-detail.markdown` typography: `p`, `ul/ol`, `li`, `code`, `pre`, `strong`, `a`. Keep 12.5px / 1.7; inline code uses a `--mono` + `--bg-inset` chip; long test names use `overflow-wrap:anywhere`; code blocks are monospace and scroll horizontally; no syntax highlighting.
- Record the data-side convention in `06 §4.1` and `05 §3.4`: `bad_case_description` allows and encourages Markdown; failure groups use small headings, test names use inline code, and each case is a list item. Historical plain text is not migrated; `breaks:true` makes existing line breaks work immediately.
- Attribution `AttributionReport.reason` stays plain text and `reasoning` stays Markdown; the split is unchanged.
- The V2 prototype `FindingDescription` follows the same contract and includes a SWE-bench demo case; production visual work uses that prototype as the baseline.

## Alternatives considered

- **Add only `white-space: pre-wrap`**: rejected. It preserves line breaks but leaves lists, inline code, emphasis, and code blocks as raw characters; it does not deliver "Markdown rendering".
- **Detect failure lists and auto-format in the frontend**: rejected. The display layer should not guess the semantics of free text; formatting differs by reporter, the rules would drift, and code blocks/links cannot be handled safely.
- **Introduce another Markdown component/library**: rejected. The same page already has a tested `renderMarkdown` with security and link hardening in place; a new dependency only adds bundle and review surface.
- **Render attribution `reason` as Markdown too**: rejected. Its semantic split from `reasoning` is "conclusion note vs reasoning"; this issue only changes the problem description and does not expand the attribution contract.
- **Convert plain text to Markdown at ingest time**: rejected. The conversion is irreversible and pollutes the authoritative external data; the display layer should only render safely and the format convention belongs to the reporting side.

## Consequences

- Existing plain-text descriptions do not get worse: without Markdown syntax they render as normal paragraphs, and single line breaks become `<br>`. But a single-line plain-text blob stays a single-line blob; grouped readability depends on the upstream side emitting Markdown.
- The security boundary reuses the existing configuration: raw HTML is escaped, external links are hardened, and there is no syntax highlighting; code blocks are monospace with horizontal scrolling.
- Component tests must cover lists, inline code, hard breaks, raw HTML, and external links; `markdown.test.ts` locks `breaks:true` and escaping so future config changes cannot regress silently.
- The V2 prototype adds one SWE-bench demo session/case (`BC-HC-027`), so session and bad-case counts grow by one; it is design-review data only and never enters production.
- The data-side format convention is parallel: until external reporting/analysis emits Markdown, the UI can only guarantee that descriptions already containing Markdown or line breaks display correctly; it cannot invent failure groups.
