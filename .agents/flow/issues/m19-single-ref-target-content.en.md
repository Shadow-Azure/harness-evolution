# Production target-content reads: single-ref shallow fetch

English | [中文](m19-single-ref-target-content.md)

```yaml flow
kind: issue
id: m19-01
milestone: m19
depends: []
priority: P2
status: in-progress
scope:
  - apps/api/**
  - .agents/**
  - plans/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 395
  url: https://github.com/Shadow-Azure/harness-evolution/issues/395
```

## Background

When the launch wizard resolves a selected version into a body hash, `SubprocessGitContent` first runs `git clone --mirror` on the target repository in the request path and then `git show`s one `SKILL.md` / `AGENT.md`. After the production data-directory migration the cache was empty, and on the mainland-to-GitHub link a full mirror cannot finish within 20 seconds, so users saw "target file read timed out" ([issue #391](https://github.com/Shadow-Azure/harness-evolution/issues/391)). Reading one ref downloaded all history and widened the failure window.

Egress proxying is a separate, orthogonal problem and is not part of this iteration: the proxy configuration, Secret, deployment, and failure fallback design lives in [#394](https://github.com/Shadow-Azure/harness-evolution/issues/394) as a later independent task.

## Goals

- Replace the per-repository mirror cache with a per-(`repo_url`, `ref`) shallow repository that fetches only the target ref.
- Use `git clone --depth 1 --single-branch --filter=blob:none` for tags/branches and `git init` plus a single-ref `fetch` for full commits; then `git show` lazily fetches one blob.
- Keep the `read_file` interface, the 20-second bound, stable failure classes, and body-hash semantics unchanged.

## Design authority

- [01 §2 Composition and layering](../../../plans/fullstack-design/01-architecture.md#2-组成与分层): target-content reads belong to the outbound-integration boundary.
- [04 §3 Layering and directories](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录): `third_party_api` isolates git processes and business rules stay in the service layer.
- [issue #391](https://github.com/Shadow-Azure/harness-evolution/issues/391): cold-clone timeout evidence and the single-ref shallow-fetch trade-off.
- [git partial clone](https://git-scm.com/docs/partial-clone): lazy blob semantics of `--filter=blob:none`.

## Implementation

- The cache key is `<data_dir>/target-content/<sha256(repo_url)[:32]>/<sha256(repo_url + "\0" + ref)[:16]>/`; a process-local lock serializes each cache path so concurrent reads cannot delete a directory another request is using.
- First tag/branch read: `git clone --depth 1 --single-branch --filter=blob:none --no-checkout --branch <ref> -- <repo_url> <dir>`; a full 40-hex commit: `git init` + `remote.origin.promisor=true` + `remote.origin.partialclonefilter=blob:none` + `git fetch --depth 1 --filter=blob:none --no-tags origin <sha>`.
- Existing cache: tags and branches run `git fetch --depth 1 --filter=blob:none --no-tags origin <ref>` to stay current; a full SHA is reused as immutable. Then `git show <FETCH_HEAD|HEAD>:<path>`, with the promisor remote fetching one blob on demand.
- Preserve stable classifications without exposing stderr: missing ref → `ref_not_found`, missing file → `file_not_found`, network/proxy unavailable → `repo_unreachable`, timeout → `timeout`, missing git → `git_unavailable`, traversal → `path_invalid`, unsafe ref → `ref_invalid`; clean partial cache directories on failure or cancellation.
- No GitHub API and no private-repository credentials; `TargetContentResolver` stays unchanged.

## Implementation steps

1. Create the m17 flow files and issue.
2. Rewrite `SubprocessGitContent` caching and single-ref fetch.
3. Add tag/branch/full-SHA, missing-ref, missing-file, cache-reuse, cleanup, and argv-assertion tests.
4. Update the Agent Note, run the gates, and open the PR.

## Dependencies and boundary

- Dependencies: none; no new Python dependency and no database or API contract change.
- Non-goals: no egress proxy (Secret, Xray deployment, proxy environment, and breaker live in #394); no change to the synchronous `preview/*` contract or asynchrony; no frontend change; no change to the run-workspace mirror/push model; no GitHub Contents API or public mirror.
- Old mirror cache directories stay in place; the new layout does not read them, so no data migration is needed.
- Full commit SHAs are fetched directly; abbreviated SHAs are no longer resolved from a local mirror and return `ref_not_found`, to be completed by a later task via the GitHub API or the caller.

## Verification

```sh
pnpm test:api
pnpm typecheck:api
pnpm verify:flow
pnpm lint:docs
```

- Unit tests: a local bare repository reads tags, branches, and full commits; cold-read argv contains `--depth 1 --single-branch --filter=blob:none` and never `--mirror`; missing refs/files return stable reasons; a reused cache does not clone again; failures clean the cache.

## Acceptance

- A cold single-ref read fetches only that ref and never `--mirror`; reading one file lazily fetches only that blob.
- Tags, branches, and full commit SHAs resolve to the same body hash; missing refs/files keep the existing error codes.
- An existing old mirror cache is unaffected and requires no migration.

## Gates and CI

- `pnpm test:api`, `pnpm typecheck:api`, `pnpm lint:api`, `pnpm verify:flow`, `pnpm lint:docs`, `pnpm contract:check`.
- `verify:flow --diff` validates the PR title and commit `(#N)` references plus scope coverage.
- New tests cover single-ref argv, cache reuse, failure classification, and cleanup.

## Non-goals

- No proxy egress or failure fallback.
- No mirror prewarming and no asynchronous `preview/*`.
- No change to run-workspace integrity or push behavior.
