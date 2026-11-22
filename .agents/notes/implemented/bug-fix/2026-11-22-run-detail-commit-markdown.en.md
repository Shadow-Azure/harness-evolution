# Agent Note: Render accepted run-detail commits as Markdown

Status: implemented

English | [中文](2026-11-22-run-detail-commit-markdown.md)

## Problem

The accepted turn panel in run-detail step 6 interpolated `finalCommit.message` into `.commit` as one line of monospace text. The backend's `build_accepted_message()` already produces multi-section Markdown: a subject line followed by `## 问题`, `## 分析`, `## 改动`, `## 追溯`, `-` lists, URLs, `---`, and `Harness-*` trailers. The browser collapsed line breaks into spaces, `##` and `---` appeared literally, and long bad-case IDs and URLs filled the card. The data and git history were correct; the display layer and the design contract were not.

The design documents only showed a one-line `finalCommit.message` example (`05 §3.6`), and `08 §10.3` only said to show the amended commit without defining how multi-section Markdown should render. The V2 prototype showed a structured summary instead. Each choice was locally valid, but together they produced the raw-text dump in the production screenshot. Component tests only asserted the hash and `Harness-Evaluated-Commit`, so the regression could ship green.

## Decision

- `StepIterations.vue` splits `finalCommit.message` into a first-line subject and the remaining body. The subject is single-line with ellipsis and keeps the full text in `title`; the body renders separately.
- Default collapsed: an accepted turn shows only the 12-character hash and subject. When the body is non-empty, a "查看完整 commit message / 收起" button toggles the body, tracked per `roundId`. Single-line legacy messages get no button.
- The body reuses the existing `renderMarkdown(..., { images: false })` and is written into `.commit-message.markdown` with `v-html`: no second Markdown library, no raw HTML, no images. Scoped `:deep()` rules cover headings, lists, links, inline code, code blocks, and rules; the body is capped at 520px and scrolls, and long URLs use `overflow-wrap: anywhere` instead of `break-all`.
- `05 §3.6` and `08 §10.3` now state the contract: `finalCommit.message` is full Markdown whose first line is the subject; the display layer must not interpolate it as plain text, and legacy single-line messages remain valid input.
- Component tests add a long-Markdown fixture and collapsed/expanded assertions; the E2E fixture's accepted turn uses the same long message, and the step-6 smoke asserts no literal markers in the default view and visible headings/lists/links after expansion.
- The V2 prototype's Option A (collapsed by default, expand on demand, Markdown rendering) already landed first and is the visual and interaction baseline for production.

## Alternatives considered

- **Render the full body as Markdown without collapsing**: rejected. It is a smaller change, but a long message still makes step 6 very tall and pushes later turns off the first screen, unlike the compact prototype card.
- **Keep only the prototype's structured summary and never show the full body**: rejected. It is closest to the prototype but loses the run/cluster/source-case traceability.
- **Add only `white-space: pre-wrap`**: rejected. It preserves line breaks but leaves lists, links, headings, and trailers as literal characters; it does not deliver Markdown rendering.
- **Introduce a Markdown component or library**: rejected. The repository already has the tested `renderMarkdown()` (`html:false`, hardened links); a new dependency only adds bundle size and review surface.
- **Shorten the commit message in the backend**: rejected. The commit body is part of git history and traceability; this issue only fixes the display layer and does not change generation or historical data.

## Consequences

- Legacy single-line messages still render as the subject with no empty body or stray button; rejected turns are unchanged.
- Long messages collapse into a compact card and need one explicit click for the full body; the 520px cap scrolls very long content inside the card instead of growing the page without bound.
- The security boundary reuses the existing renderer: raw HTML is escaped, external links get `target="_blank"` and `rel="noopener noreferrer"`, and Markdown images in the commit degrade to alt text.
- The E2E fixture's `v2-round-1` uses a long Markdown message, so the step-6 smoke and screenshots run on reproducible data; production run IDs, session content, and production screenshots stay out of the repository.
- No API, `packages/contracts`, database, or commit-message generation change; issue #482 stays open until the requester confirms the whole flow is clean.
