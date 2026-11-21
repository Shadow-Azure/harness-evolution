# Rewrite the README: project introduction, capabilities and one key screenshot

English | [中文](m27-readme-showcase.md)

```yaml flow
kind: issue
id: m27-01
milestone: m27
depends: []
priority: P2
status: ready
scope:
  - README.md
  - README.en.md
  - README.i18n.yaml
  - docs/assets/readme/**
  - scripts/doc-budgets.manifest.json
  - docs/**
  - .agents/**
adr: []
github:
  number: 461
  url: https://github.com/Shadow-Azure/harness-evolution/issues/461
```

## Background

The root `README.md` still opens with "M1 engineering foundation in progress", and its body is mostly quick start, production prerequisites and the directory layout. It does not answer what new readers care about most: what problem this project solves, what it can do today, and what the product looks like. The project has shipped through M25 (workspaces, trace normalization, multi-attribution, the seven-step evolution and the lane DAG), so that status text is out of date and disagrees with the "available / not yet available" list in `docs/architecture.md`.

Common high-star READMEs build the first screen from a one-sentence positioning, a set of capability highlights, one product screenshot and a copyable quick start, then link to detailed docs. This issue rewrites the root README around that structure and adds one key screenshot from local fixtures. Production is used only for manual inspection; no production session content or screenshot is committed.

## Goals

- State the service positioning in one sentence, and cover trace inspection, problem attribution, the evolution loop and engineering boundaries under "core capabilities".
- Show one product screenshot on first visit: the session browser, the execution-flow lane DAG and problem cards. The screenshot comes from synthetic data seeded by local `pnpm fixtures:seed` and contains no production content.
- Keep a copyable local quick start; production deployment, architecture and development details stay in `docs/`, and the README only links to them.
- Keep the Chinese and English sides structurally mirrored and re-record the pairing; `README.md` remains the Chinese base.
- Commit the screenshot as a versioned static asset under `docs/assets/readme/` with a path that renders on GitHub.

## Design authority

- [02 §2 Feature details](../../../plans/fullstack-design/02-features.md): capability bullets follow the session-error, evolution and cross-cutting feature points.
- [01 §2 Components and layers](../../../plans/fullstack-design/01-architecture.md): the layout after quick start describes the real layers such as `apps/web`, `apps/api` and `packages/contracts`.
- [01 §5.3 Demo-data boundary](../../../plans/fullstack-design/01-architecture.md): the screenshot uses fixture demo data; no production session, prompt, document body or credential is committed.
- [docs/AGENTS.md](../../../docs/AGENTS.md) and [docs/i18n/README.en.md](../../../docs/i18n/README.en.md): the root README is a resident document and needs a bilingual pair, a word budget and a re-recorded pairing.
- [Best-README-Template](https://github.com/othneildrew/Best-README-Template): the common ordering of positioning → screenshot → capabilities → quick start → documentation entry points.

## Implementation

- `README.md`: replace the M1 status section, add the product screenshot, core capabilities, quick start and documentation entry points, and remove the production prerequisites duplicated from `docs/deployment.md` while keeping a pointer.
- `README.en.md`: rewrite the English side with the same structure, switch links to `.en.md`, and keep code-fence content byte-identical to the Chinese side.
- `docs/assets/readme/session-overview.png`: capture the session browser, execution flow and problem cards in the local fixture demo at 1440×900, 2× DPR and the light theme; the image contains only synthetic data and the "demo data" badge.
- `README.i18n.yaml`: re-record both blob hashes; `verify:docs` checks the structural mirror.
- `scripts/doc-budgets.manifest.json`: raise the `README.md` budget from 400 to 500 because the rewrite adds positioning, capabilities and screenshot context while moving production deployment details out of the README; the PR explains the adjustment.
- Add one `process` Agent Note recording the README audience, the screenshot data boundary and the choice to keep a single screenshot.

## Implementation steps

1. Log in to the local fixtures environment and capture the session detail page, confirming that only synthetic data and the "demo data" badge appear.
2. Rewrite the Chinese and English READMEs as positioning → screenshot → capabilities → quick start → documentation → layout, and remove the stale M1 status and duplicated deployment section.
3. Add the image asset and Agent Note, adjust the word budget, and re-record the README pairing.
4. Run `pnpm lint:docs`, `pnpm verify:docs` and `pnpm verify:flow`; check the rendered image path and links.
5. Commit and open a PR whose title carries the issue number; the PR description states the screenshot source and the budget reason.

## Dependencies and boundary

- Depends on: no code dependency; uses the existing `pnpm fixtures:seed` and local demo environment.
- Delivery: bilingual README, image asset, Agent Note, budget and pairing record; no application code, API, contract or UI change.
- Boundary: no production screenshot or session content; no second screenshot, GIF or video; no deployment details moved into the README.

## Verification

```sh
node --input-type=module -e "import { countWords } from './scripts/verify-doc-budgets.mjs'; import { readFileSync } from 'node:fs'; console.log(countWords(readFileSync('README.md','utf8')))"
pnpm lint:docs
pnpm verify:docs
pnpm verify:flow
```

- The word count is ≤ 500; `lint:docs` and `verify:docs` pass, including pairing, dead links, image paths and paragraph wrapping; `verify:flow` passes.
- Render the README locally and confirm that the screenshot is visible, the caption says "local synthetic fixtures", and every relative link resolves.
- Use `git diff --stat` to confirm that only the README, image, Note, budget and flow files changed.

## Acceptance

- The first screen of the README shows the positioning, key screenshot and capability summary; the quick-start commands can be copied and run.
- The README matches the current capabilities in `docs/architecture.md` and no longer says "M1 engineering foundation in progress".
- The Chinese and English sides mirror each other and the pairing record matches; the image is committed and renders on GitHub.
- No production session content, prompt, credential or real user data enters the repository.
- Document, flow and pairing gates are green.

## Gates and CI

- Document gates: `lint:docs` and `verify:docs` (word budget, pairing, dead links, image paths, paragraph wrapping).
- Flow gates: `verify:flow`, with `verify:flow --diff` checking the title and scope during the PR.
- The CI docs-flow lane covers these checks; no new code tests are added.

## Non-goals

- Do not change the application UI, interaction, routing or product behavior beyond the screenshot.
- Do not rewrite the architecture, deployment or development docs under `docs/`; only remove the duplicated deployment section from the README and keep the link.
- Do not add badges, a GIF, a video or multiple screenshots; do not alter or fabricate production data.
- Do not adjust bilingual documents outside the README.
