# Body-hash identity and post-process anchor for attribution

English | [中文](m13-body-hash-post-process-anchor.md)

```yaml flow
kind: issue
id: m13-01
milestone: m13
depends: []
priority: P2
status: in-progress
scope:
  - .agents/flow/**
  - .agents/notes/**
  - plans/fullstack-design/**
  - plans/**
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - scripts/doc-budgets.manifest.json
  - apps/api/**
  - apps/api/alembic/**
  - apps/api/tests/**
  - apps/web/src/**
  - packages/contracts/**
  - tests/**
  - fixtures/**
adr:
  - ../../notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.md
github:
  number: 368
  url: https://github.com/Shadow-Azure/harness-evolution/issues/368
```

## Background

In the 2026-11-18 production test the `skill / systematic-debugging` target at `v6.4.1` associated zero Sessions at step 2: all four normalized Sessions were skipped and eighteen were pending. The trace event only has `definitionHash=8e54…` and `objectRevision=digest:3643…`; the latter includes the runtime-injected skill source path. That path is a plugin-cache path such as `.../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md`; it is not a stable relative path and is not persisted, so the target cannot reconstruct the same revision from `repoUrl/subDir/ref`. The owner confirms the target should use `superpowers` `main`. The eval trace is now available: its skill body hash is `8e54…`; main's `SKILL.md` whole-file hash is `a9a7…`, and after removing the YAML frontmatter its body hash is exactly `8e54…`; v6.4.1's whole-file `9080…` was the same body plus frontmatter. The root cause was the target resolver hashing the whole file without stripping frontmatter; after the fix, resolver and parser both reach `digest:8e54…`, so the source alignment and M13 acceptance item are resolved.

Meanwhile, `eventIndex=-1` currently means "missing/abnormal anchor" and degrades to the reporting Agent's birth point (the Session start for a main Agent). The 22 production cases are discovery + agent + main reporter; under the current rule they always fall before the target object and potential is zero. "Post-process report" has no dedicated semantics and cannot be explained or matched as "after the object".

The design docs and implementation currently use the path+body identity (`docs/architecture.md:42`, `15 §9.2`, `06 §7.5`, `07 §5.12`), while skill/agent/knowledge file matching should all use `sha256(normalize_definition_body(body))`: skill `SKILL.md`, agent `AGENT.md`/`agent.md`, knowledge document file reads. The current target content resolver covers only the skill tag file; knowledge matching still uses `provider:`/original revisions. This issue must put the shared key, tag/document-revision resolution, compatibility, and migration into the design docs before implementation. The current code already declares parser_version 5 (M9-05 knowledge); the new identity needs 5→6. A bare knowledge revision needs a `KnowledgeContentSource`: without a document Provider in production only `digest:`/`provider:` can launch directly, and a bare revision returns `TARGET_CONTENT_UNRESOLVED`.

## Goals

- Unify the **file-matching key** for skill/agent/knowledge to `sha256(normalize_definition_body(body))`: skill `SKILL.md`, agent `AGENT.md`/`agent.md`, knowledge document file reads. The source path is evidence only and does not participate in revision, cache keys, or matching. Skill identity uses this body hash; an agent `object_revision` keeps type/builtin evidence identity but matching uses `definition_hash`; knowledge `document_revision`/`object_revision` also use the normalized body hash.
- Treat the tag selected in the evolution wizard as the content source: for skill/agent the server reads `SKILL.md`/`AGENT.md` at that tag, and for knowledge it reads the document at its revision; all use the same normalizer to compute the body hash as `targetRevision`. The tag/document revision remains the version/display and code baseline. Knowledge targets remain API-configured/API-launched; the wizard has no knowledge selector yet.
- Change post-processed cases whose reported object cannot be found to an explicit post-process anchor: `eventIndex=INT_MAX`, `anchorKind=post_process`, `triggeredAt=created_at`; they participate in potential matching as "after the object". `-1` remains only for an unresolvable reporting Agent.
- Define the parser version, replay, legacy path+body revisions and cache keys, contract/UI display, and test plan; implementation follows design review.

## Design authority

- [15 §9.2 object revision and model identity](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)
- [06 §7.4 problem-side semantics](../../../plans/fullstack-design/06-database-design.md), [§7.5 V2 semantics](../../../plans/fullstack-design/06-database-design.md)
- [05 §4.20 preview and launch](../../../plans/fullstack-design/05-api-design.md), [§3.4 problem and attribution DTOs](../../../plans/fullstack-design/05-api-design.md)
- [07 §2.6 multi-runtime parser factory](../../../plans/fullstack-design/07-backend-implementation.md), [§5.12 potential matching](../../../plans/fullstack-design/07-backend-implementation.md), [§5.13 attribution generation and cache](../../../plans/fullstack-design/07-backend-implementation.md)
- [08 frontend implementation](../../../plans/fullstack-design/08-frontend-implementation.md)
- [Architecture: evidence and revision](../../../docs/architecture.en.md)
- [Agent Note: body-hash identity and post-process anchors](../../notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.en.md)

## Implementation

- Design docs: update the sections above in 15/06/05/07/08 and `docs/architecture.md` (both languages) with the shared skill/agent/knowledge body-hash file matching, tag/document-revision resolution, post-process anchors, compatibility, and migration; add a proposed Agent Note recording the decision and rejected alternatives.
- Follow-up code (tracked, not in the design-doc PR): parser skill identity, agent `definition_hash`, and knowledge file-read revision become the normalized body hash with a parser version bump; the target content resolver reads `SKILL.md`/`AGENT.md` at the tag or the knowledge document at its revision, normalizes, computes the hash, and adds caching and stable errors; the matcher accepts body hash and legacy path+body (transition) and implements the post-process anchor; candidate/attribution snapshots record `anchorSource`; contracts, API DTOs, frontend display, and tests follow.
- Migration: replay stored claude-code Sessions by parser version for skill/agent/knowledge; parser_version 5→6; legacy path+body revisions remain historical and new runs write the normalized body hash; old cache keys are not reused; the 96-character `probe_reports.object_version` is sufficient. Bare knowledge revisions need a document Provider; production has none, while `digest:`/`provider:` launch directly.

## Implementation steps

1. Create the M13 issue and proposed Note; update 15/06/05/07/08, `docs/architecture.md` and the English side, i18n pairs; open a docs-only PR for review.
2. After review, implement the parser body-only revision, version bump, and replay; add unit/fixture tests.
3. Implement the target content resolver: skill/agent tag to `SKILL.md`/`AGENT.md`, knowledge document revision to content; normalize, cache, timeout, stable errors; add golden hash tests proving agreement with a known trace `definitionHash`/`documentRevision`.
4. Implement the matcher body-hash match and post-process anchor; update candidate/attribution snapshots, contracts, and frontend display.
5. Run migration, replay, and cross-stack tests; update docs status and commands.

## Dependencies and boundary

- Dependencies: M12 is complete; M13 design review precedes code.
- Non-goals: no knowledge UI selector (knowledge remains API-configured/API-launched; resolver/matcher are in scope); no private-repository credentials; no rewrite of rule-v1 categories; no code in the design-doc PR.

## Verification

```sh
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
pnpm test:gates
```

- `verify:flow` passes and the issue trio agrees with the M13 milestone.
- `lint:docs` / `verify:docs` pass; `docs/architecture.md`, its English side, and the i18n record agree.
- Code phase adds: golden tests that skill/agent tag content and knowledge document content's normalized sha256 equal a known trace `definitionHash`/`documentRevision`; API/integration tests for `anchorKind=post_process`, `eventIndex=INT_MAX`, `triggeredAt=created_at`, and `after_object`.

## Acceptance

- The design docs state that skill/agent/knowledge file matching all use the normalized body hash, with the source path no longer participating; skill/agent tags and the knowledge document revision are content sources; post-process cases with no object use an explicit, auditable anchor.
- The design docs define the compatibility boundary for legacy path+body revisions, parser version, replay, cache keys, and contracts/UI.
- Golden hash tests prove all three target content sources match the trace body; a mismatch returns a stable error and never falls back to tag guessing.
- Code starts only after design review; the issue stays open until implementation completes.

## Gates and CI

- This PR: `verify:flow`, `lint:docs`, `verify:docs`, `test:gates`.
- Code phase: `test:api`, `test:db`, `contract:check`, relevant e2e and migration tests; regenerate contracts.

## Non-goals

- No knowledge UI selector; knowledge remains API-configured/API-launched.
- No private-repository credentials or new deployment secrets.
- No parser, matcher, contract, or frontend code before design review.
