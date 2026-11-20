# Fetch a single ref for evolution run workspaces and preserve iteration and push

English | [中文](m22-single-ref-run-workspace.md)

```yaml flow
kind: issue
id: m22-01
milestone: m22
depends:
  - m19-01
priority: P0
status: ready
scope:
  - apps/api/**
  - deploy/**
  - docs/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 411
  url: https://github.com/Shadow-Azure/harness-evolution/issues/411
```

## Background

In the prepare stage, production self-evolution runs `git clone --mirror` through `GitWorkspaceManager._ensure_mirror`, downloading every ref and all history into `data_dir/repos/<targetId>`. For `obra/superpowers@v6.4.1` the full mirror measured 290MB, while a single-branch full-history clone of the same ref needs only 7.1MB (pack 3.87MiB), a depth-1 clone 3.3MB, and a sparse subdirectory clone 520KB. The fixed 60-second clone limit has repeatedly failed on cross-border links: runs 01M7T5AA and 01M7T729 both failed in the prepare clone stage after 60.0 seconds, and a failed clone deletes the partial mirror so every retry starts from zero. The m18 egress proxy is live, but 290MB is still not reliable within 60 seconds.

m19 changed only target-content reads and explicitly left the run workspace mirror/push model alone; this issue covers that layer. On push, `git_push` defaults to true, so prepare already pushes the run branch to `origin`; a third-party public repository without write access will then fail at the push stage. The push target and credential policy therefore need to be explicit here as well.

## Goals

- A run workspace cold clone fetches only the target ref (branch / tag / full commit) and never runs `--mirror`; a target repository clone lands in the 10MB class and completes within 60 seconds.
- The cache keys on target + ref, with an explicit fetch when the ref changes; transient failures keep complete objects, and partial cleanup and retry are explicit.
- A single-ref clone supports creating the run branch, writing a patch, committing, passing ancestry checks, and pushing, with the same behavior as the full-mirror flow.
- Run events record the clone ref, cache hit, duration, and proxy state (disabled / closed / open), so proxy usage is answerable without SSH.
- The push target and credential policy are explicit: by default, do not push a branch to a third-party repository without write access; when pushing is required, use a writable fork / push URL and credentials.

## Design authority

- [04 §3 Layering and directories](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录): `third_party_api` isolates git processes and business rules stay in services.
- [04 §9 Configuration list](../../../plans/fullstack-design/04-backend-architecture.md#9-配置项清单): ownership of git-side settings such as `HE_GIT_PROXY` and `HE_GIT_PUSH`.
- [01 §2 Composition and layering](../../../plans/fullstack-design/01-architecture.md#2-组成与分层): git reads and workspaces belong to the outbound-integration boundary.
- [issue #395](https://github.com/Shadow-Azure/harness-evolution/issues/395): the existing single-ref shallow target-content implementation and failure classification.
- [issue #397](https://github.com/Shadow-Azure/harness-evolution/issues/397): the git egress proxy and direct-fallback boundary.
- [git partial clone](https://git-scm.com/docs/partial-clone): on-demand blobs and the `--filter=blob:none` semantics.

## Implementation

- `apps/api/app/third_party_api/git/workspace.py`: replace `_ensure_mirror` with a target + ref `_ensure_ref_cache`. For a tag / branch, run `git init --bare` plus `git fetch --no-tags origin <ref>:<local-ref>`; for a full commit, run `git fetch --depth 1 --no-tags origin <sha>`; `--mirror` is no longer used. The cache key contains the target and the normalized ref, a process lock serializes access, and a ref change triggers an explicit fetch.
- `prepare`: the workspace still runs `git clone --no-checkout` from the local cache, then `git switch -c evo/<date>-<runId> <base>` and `remote set-url origin <repo_url>`; branch/patch/commit/push behavior is unchanged.
- Failure and cleanup: transient failures keep already-complete objects; partial directories are cleaned up under the existing policy and can be retried; error classification keeps the `clone` / `reference` / `workspace` / `push` boundary and never exposes stderr or credentials.
- Run events: add `ref`, `cacheHit`, `cloneSeconds`, and `proxyState` (`disabled` / `closed` / `open`) to the prepare/clone event payload; never record proxy credentials or configuration content. The fields are additive and do not change existing consumers.
- Push: keep `HE_GIT_PUSH`; add an optional push URL (fork / push URL) or explicitly require disabling push for third-party targets; credentials come only from the runtime environment / credential helper and never enter the repository or database. Do not silently push a branch to a target without write access.
- Tests: assert argv never contains `--mirror`; cover tags, branches, full SHAs, cache reuse, ref-change refresh, missing refs, and failure cleanup; cover prepare → patch → commit → ancestry → push (local bare remote) and the event payload.
- Docs: update the git workspace / deployment configuration docs and the Agent Note with the trade-offs of single-ref cloning, caching, and push credentials.

## Implementation steps

1. Design and implement the target + ref cache and single-ref fetch, with argv, ref-type, cache-hit, and refresh tests.
2. Wire prepare / workspace / push and add commit, ancestry, push, and failure-cleanup tests.
3. Add ref, cache, duration, and proxy-state fields to run events with API tests.
4. Make the push target and credential configuration explicit, add validation and docs, and default third-party targets to no push.
5. Update the Agent Note and design docs, run the gates, and measure a real single-ref clone.

## Dependencies and boundary

- Depends on: m19-01 (single-ref shallow target-content reads).
- Boundary: change only the run workspace clone/cache/push boundary; do not touch the m18 proxy implementation, m19 target-content reads, patch generation, evaluation, frontend, or the `preview/*` contract.
- The old full-mirror cache directories are not migrated; the new layout reads by target + ref. Push credentials never enter the repository.

## Verification

```sh
pnpm test:api
pnpm typecheck:api
pnpm verify:flow
pnpm lint:docs
```

- Unit tests: a local bare repository supports tag, branch, and full SHA targets with only the target ref fetched; argv contains no `--mirror`; a cache hit does not clone again; a ref change triggers a fetch; failure classification and cleanup match expectations; prepare → commit → push works against a local bare remote.
- Measurement: `git clone --branch v6.4.1 --single-branch --no-tags https://github.com/obra/superpowers /tmp/sp` produces a pack of about 3.9MiB and finishes well under 60 seconds; the run workspace code no longer contains `--mirror`.

## Acceptance

- A run workspace cold clone no longer runs `--mirror`; tags, branches, and full commits fetch only the target ref.
- A single-ref clone supports creating the run branch, writing a patch, committing, passing ancestry checks, and pushing; the push target/credential policy is explicit and third-party targets without write access do not receive a branch by default.
- The cache keys on target + ref and supports hit/refresh; transient failures do not discard complete objects, and partial caches can be retried.
- Run events include ref, cacheHit, cloneSeconds, and proxyState, so proxy usage is directly answerable.
- Existing API, contracts, frontend, and evaluation contracts are unchanged; the target repository clone completes within the 60-second limit.

## Gates and CI

- `pnpm test:api`, `pnpm typecheck:api`, `pnpm lint:api`, `pnpm verify:flow`, `pnpm lint:docs`; if event fields enter OpenAPI, also run `pnpm contract:check`.
- `verify:flow --diff` checks the PR title and commits for `(#N)` and scope coverage.
- New tests cover single-ref argv, cache reuse/refresh, ref types, push, and event fields.

## Non-goals

- No Xray / VLESS proxy, Secret, or deployment-fallback changes (m18).
- No target-content cache or 20-second-limit changes (m19).
- No patch generation, evaluation, frontend, preview-contract, or seven-step state-machine changes.
- No push credentials in the repository or database; no default push to a third-party public repository.
