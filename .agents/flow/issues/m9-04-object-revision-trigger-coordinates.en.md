# Object revision parsing, trigger coordinates, and replay

English | [中文](m9-04-object-revision-trigger-coordinates.md)

```yaml flow
kind: issue
id: m9-04
milestone: m9
depends:
  - m9-02
  - m9-03
priority: P0
status: done
scope:
  - apps/api/app/service/acquisition/**
  - apps/api/app/db/**
  - apps/api/alembic/**
  - packages/contracts/**
  - tests/**
  - apps/api/tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 239
  url: https://github.com/Shadow-Azure/harness-evolution/issues/239
```

## Background

Real skill listings can expose content summaries and an opaque 16-hex digest without a semantic version, while subagent prompt_snapshot contains the agent definition body. Comparing only targetVersion misses whole Sessions, and relying on skill_listing.digest is unsafe until its algorithm is confirmed.

## Goals

- Support tag, digest, and unknown object revisions.
- Prefer skill path + normalized body hash; use listing digest only as fallback.
- Build agent revision from agentType + isBuiltIn + systemPrompt[0] body hash.
- Persist tree_index, triggered_at, and stable event coordinates.
- Replay with a parser version bump to form comparable evidence.

## Design authority

- [15 §9.2–§9.3](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#92-对象-revision-与模型身份): revisions and trigger rules.
- [06 §7.5](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态): object entry points and comparison.
- [07 §2.6 Multi-runtime parser factory](../../../plans/fullstack-design/07-backend-implementation.md#26-多-runtime-parser-工厂): runtime boundary for evidence hooks.

## Implementation

- Parse Skill meta path/body hash and agent prompt_snapshot/definition hash.
- Keep skill_listing digest only as an opaque fallback; it is not a primary key until its algorithm is confirmed.
- Store explicit tool triggers separately from attributionSkill.
- Prefer triggered_at, fall back to coordinate ordering, and mark missing coordinates unknown.
- Replay only the runtime whose parser version changed.

## Implementation steps

1. Write tag/digest/body-hash/unknown tests.
2. Implement trigger coordinates and parser-version incremental replay.
3. Verify definition hashes are stable across tasks and isolated across runtimes.
4. Verify legacy data never falls back to name guessing.

## Dependencies and boundary

- Dependencies: m9-02, m9-03
- Boundary: no PotentialMatcher.

## Verification

```sh
pnpm test:api -- tests/acquisition; pnpm data:replay:sessions; pnpm test:db
```

- The same skill body matches across sessions.
- Two tasks of the same agent type produce the same definition hash.
- No body and no tag means unknown.
- skill_listing digest is a fallback only after its algorithm is confirmed.
- Trigger order is comparable across agents after replay.

## Acceptance

- Identity no longer depends on a single version or a name.
- Unknown revisions have explicit reasons.
- Skill/agent bodies are not stored; only path/hash/source are.

## Gates and CI

- API, database, replay, and flow gates.

## Non-goals

- Do not equate equal names with equal versions.
- Do not store full skill or agent definitions.
- Do not depend on an unconfirmed skill_listing digest algorithm.
