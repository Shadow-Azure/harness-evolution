# Body-hash identity and post-process anchor for attribution

English | [中文](m13-body-hash-post-process-anchor.md)

```yaml flow
kind: issue
id: m13-01
milestone: m13
depends: []
priority: P1
status: in-progress
scope:
  - .agents/flow/**
  - .agents/notes/**
  - plans/fullstack-design/**
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - scripts/doc-budgets.manifest.json
  - apps/api/app/service/acquisition/**
  - apps/api/app/service/evolution/**
  - apps/api/app/db/**
  - apps/api/alembic/**
  - apps/api/tests/**
  - apps/web/src/**
  - packages/contracts/**
  - tests/**
  - fixtures/**
adr:
  - ../../notes/proposed/architecture/2026-11-18-body-hash-attribution-post-process.md
github:
  number: 368
  url: https://github.com/Shadow-Azure/harness-evolution/issues/368
```

## Background

In the 2026-11-18 production test the `skill / systematic-debugging` target at `v6.4.1` associated zero Sessions at step 2: all four normalized Sessions were skipped and eighteen were pending. The trace event only has `definitionHash=8e54…` and `objectRevision=digest:3643…`; the latter includes the runtime-injected skill source path. That path is a plugin-cache path such as `.../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md`; it is not a stable relative path and is not persisted, so the target cannot reconstruct the same revision from `repoUrl/subDir/ref`. In the test, `obra/superpowers` v6.4.1 has a normalized file hash of `9080…`, not the trace's `8e54…`; the source/version or body extraction still needs alignment.

Meanwhile, `eventIndex=-1` currently means "missing/abnormal anchor" and degrades to the reporting Agent's birth point (the Session start for a main Agent). The 22 production cases are discovery + agent + main reporter; under the current rule they always fall before the target object and potential is zero. "Post-process report" has no dedicated semantics and cannot be explained or matched as "after the object".

The design docs and implementation currently use the path+body identity (`docs/architecture.md:42`, `15 §9.2`, `06 §7.5`, `07 §5.12`), which conflicts with "drop source; associate by normalized body hash only". This issue must put the new semantics, compatibility, and migration into the design docs before implementation.

## Goals

- Change the skill object identity to `digest:sha256(normalize_definition_body(body))`; the source path is evidence only and does not participate in revision, cache keys, or matching.
- Treat the tag selected in the evolution wizard as the content source: the server reads `SKILL.md` at that tag and computes the body hash with the same normalizer as `targetRevision`; the tag remains the version/display and code baseline.
- Change post-processed cases whose reported object cannot be found to an explicit post-process anchor: `eventIndex=INT_MAX`, `anchorKind=post_process`, `triggeredAt=created_at`; they participate in potential matching as "after the object". `-1` remains only for an unresolvable reporting Agent.
- Define the parser version, replay, legacy path+body revisions and cache keys, contract/UI display, and test plan; implementation follows design review.

## Design authority

- [15 §9.2 object revision and model identity](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)
- [06 §7.4 problem-side semantics](../../../plans/fullstack-design/06-database-design.md), [§7.5 V2 semantics](../../../plans/fullstack-design/06-database-design.md)
- [05 §4.20 preview and launch](../../../plans/fullstack-design/05-api-design.md), [§3.4 problem and attribution DTOs](../../../plans/fullstack-design/05-api-design.md)
- [07 §2.6 multi-runtime parser factory](../../../plans/fullstack-design/07-backend-implementation.md), [§5.12 potential matching](../../../plans/fullstack-design/07-backend-implementation.md), [§5.13 attribution generation and cache](../../../plans/fullstack-design/07-backend-implementation.md)
- [08 frontend implementation](../../../plans/fullstack-design/08-frontend-implementation.md)
- [Architecture: evidence and revision](../../../docs/architecture.en.md)
- [Agent Note: body-hash identity and post-process anchors](../../notes/proposed/architecture/2026-11-18-body-hash-attribution-post-process.en.md)

## Implementation

- Design docs: update the sections above in 15/06/05/07/08 and `docs/architecture.md` (both languages) with body-only identity, tag-to-body-hash resolution, post-process anchors, compatibility, and migration; add a proposed Agent Note recording the decision and rejected alternatives.
- Follow-up code (tracked, not in the design-doc PR): parser skill revision becomes body-only with a parser version bump; the target content resolver reads `SKILL.md` at the tag, normalizes, computes the hash, and adds caching and stable errors; the matcher accepts body hash and legacy path+body (transition) and implements the post-process anchor; candidate/attribution snapshots record `anchorSource`; contracts, API DTOs, frontend display, and tests follow.
- Migration: replay stored claude-code Sessions by parser version; legacy path+body revisions remain historical and new runs write body-only; old cache keys are not reused; the 96-character `probe_reports.object_version` is sufficient.

## Implementation steps

1. Create the M13 issue and proposed Note; update 15/06/05/07/08, `docs/architecture.md` and the English side, i18n pairs; open a docs-only PR for review.
2. After review, implement the parser body-only revision, version bump, and replay; add unit/fixture tests.
3. Implement the target tag-to-content resolver (read, normalize, cache, timeout, stable errors); add a golden hash test proving agreement with a known trace `definitionHash`.
4. Implement the matcher body-hash match and post-process anchor; update candidate/attribution snapshots, contracts, and frontend display.
5. Run migration, replay, and cross-stack tests; update docs status and commands.

## Dependencies and boundary

- Dependencies: M12 is complete; M13 design review precedes code.
- Non-goals: no change to knowledge-target revision semantics; no private-repository credentials; no rewrite of rule-v1 categories; no code in the design-doc PR.

## Verification

```sh
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
pnpm test:gates
```

- `verify:flow` passes and the issue trio agrees with the M13 milestone.
- `lint:docs` / `verify:docs` pass; `docs/architecture.md`, its English side, and the i18n record agree.
- Code phase adds: a golden test that the tag content's normalized sha256 equals a known trace `definitionHash`; API/integration tests for `anchorKind=post_process`, `eventIndex=INT_MAX`, `triggeredAt=created_at`, and `after_object`.

## Acceptance

- The design docs state that the skill identity no longer includes the source path; the tag is the content source and the body hash is `targetRevision`; post-process cases with no object use an explicit, auditable anchor.
- The design docs define the compatibility boundary for legacy path+body revisions, parser version, replay, cache keys, and contracts/UI.
- A golden hash test proves the target content and trace body share a source; a mismatch returns a stable error and never falls back to tag guessing.
- Code starts only after design review; the issue stays open until implementation completes.

## Gates and CI

- This PR: `verify:flow`, `lint:docs`, `verify:docs`, `test:gates`.
- Code phase: `test:api`, `test:db`, `contract:check`, relevant e2e and migration tests; regenerate contracts.

## Non-goals

- No change to knowledge-target revision and matching.
- No private-repository credentials or new deployment secrets.
- No parser, matcher, contract, or frontend code before design review.
