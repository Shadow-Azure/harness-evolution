# Agent Note: The README as a project entry point and the screenshot data boundary

Status: implemented

English | [中文](2026-11-21-readme-showcase.md)

## Problem

The root `README.md` long stayed at "M1 engineering foundation in progress", with a body centered on quick start, production prerequisites and the directory layout. The project has shipped workspaces, trace normalization, multi-attribution, the seven-step evolution and the lane DAG, yet new readers see neither the product positioning nor the interface. Meanwhile `docs/architecture.md` already maintains the "available / not yet available" state, so the README became a second copy of stale information.

The README also needs a product screenshot, but repository rules explicitly forbid committing production session content, screenshots or credentials. Capturing production would leak internal data and make the image drift with production; text alone cannot show what the product looks like. The README word budget is only 400, so adding positioning, capabilities and screenshot context necessarily exceeds it and needs an explicit budget decision.

## Decision

- The first screen of the README answers "what it is, what it does, what it looks like": one positioning sentence, one key screenshot and four capability highlights, followed by quick start, documentation entry points and layout.
- Keep exactly one screenshot: the session detail page with the session browser, execution-flow lane DAG and problem cards. It covers trace inspection, execution flow and evidence links together, which represents the product better than the overview or run detail.
- Capture the screenshot from synthetic data seeded by local `pnpm fixtures:seed`, keep the "demo data" badge and say "local synthetic fixtures" in the caption. Do not capture production and do not alter or fabricate production data.
- Move production prerequisites out of the README; `docs/deployment.md` is the only home. The README only links to architecture, development, deployment, the documentation map, the development flow and decision records.
- Raise the `README.md` word budget from 400 to 500 because the first screen adds positioning, capabilities and screenshot context while a duplicated deployment section moves out. This is headroom left after moving and compressing, not unbounded growth.

## Alternatives considered

- **Keep the status page and append a screenshot at the end.** The first screen still cannot answer "what it is", and readers only see the product after the quick start; rejected.
- **Capture a production session page.** Easiest and most representative of real data, but it violates the rule that production session content, screenshots and credentials never enter the repository, and the image drifts with production data; rejected.
- **Use a screenshot of the `plans/ui-prototype-v2` prototype.** More polished, but a prototype is not the running application and would mislead readers into thinking the delivered product matches it; rejected.
- **Add several screenshots (overview, session, error detail, run detail).** More complete, but a longer first screen and double the maintenance, while one session page already covers the core path; rejected.
- **Keep the 400-word budget by deleting the layout or documentation links.** It could fit near 400, but the README loses navigation value; after moving and compressing, raising the budget is the better trade-off; rejected.

## Consequences

- The README's current-state description aligns with `docs/architecture.md` again; deployment, architecture and development details are no longer copied into the README.
- The screenshot is synthetic demo data and is not evidence of production capability or data scale; when the UI changes, re-capture it to the same path.
- The README budget becomes 500; future additions should move to `docs/` first rather than raising the ceiling again.
- The Chinese and English sides stay paired, the screenshot path is identical in both READMEs, and captions are translated per language.
