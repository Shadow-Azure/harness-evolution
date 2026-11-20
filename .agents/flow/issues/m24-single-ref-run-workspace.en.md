# Single-ref clones and iterative pushes for evolution run workspaces

English | [中文](m24-single-ref-run-workspace.md)

```yaml flow
kind: issue
id: m24-01
milestone: m24
depends:
  - m19-01
priority: P2
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

During prepare, production evolution runs let `GitWorkspaceManager._ensure_mirror` run `git clone --mirror` against the target repository, downloading every ref and all history into `data_dir/repos/<targetId>`. A full mirror of the target `obra/superpowers@v6.4.1` measured 290MB; all history of the one relevant branch is only 7.1MB (pack 3.87MiB), depth 1 is 3.3MB, and a sparse subdirectory is 520KB. The fixed 60-second clone bound failed repeatedly on cross-border links: runs 01M7T5AA and 01M7T729 both spent 60.0 seconds in the prepare clone stage and failed, and the half-finished mirror was deleted so retries started from zero. The m18 egress proxy is live, but 290MB is still unreliable within 60 seconds.

m19 changed only target-content reads to a single-ref shallow fetch and explicitly left the run-workspace mirror/push model unchanged; this issue covers that layer. For pushes, `git_push` defaults to true, so prepare already pushes the run branch to `origin`; a third-party public repository without write access then fails at push, so this issue must also make the push target and credential policy explicit.

## Goal

- A cold run-workspace clone fetches only the target ref (branch / tag / full commit) instead of `--mirror`; one clone drops to the 10MB class and finishes within 60 seconds.
- The cache hits and refreshes per target + ref; a changed ref triggers an explicit fetch; transient failures keep complete objects, and partial cleanup and retry are explicit.
- A single-ref clone can create the run branch, write a patch, commit, pass ancestry validation, and push, matching the existing full-mirror behavior.
- Run events and structured logs record whether each git operation (ls-remote / clone / fetch / push) used the proxy, proxy state changes, fallback reasons, and duration; no SSH session is needed to answer which operations of a run used the proxy.
- The push target and credential policy is explicit: do not push branches to third-party repositories without write access by default; when pushing is needed, use a writable fork / push URL and credentials.

## Design basis

- [04 §3 Layering and directories](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录): `third_party_api` isolates git processes while business rules stay in service.
- [04 §9 Configuration inventory](../../../plans/fullstack-design/04-backend-architecture.md#9-配置项清单): ownership of git-side settings such as `HE_GIT_PROXY`, `HE_GIT_PUSH`, and `HE_GIT_PUSH_URL`.
- [01 §2 Composition and layering](../../../plans/fullstack-design/01-architecture.md#2-组成与分层): git reads and workspaces sit on the outbound-integration boundary.
- [issue #395](https://github.com/Shadow-Azure/harness-evolution/issues/395): the existing single-ref target-content implementation and its failure classes.
- [issue #397](https://github.com/Shadow-Azure/harness-evolution/issues/397): the boundary between the git egress proxy and direct fallback.
- [git partial clone](https://git-scm.com/docs/partial-clone): on-demand blobs and the `--filter=blob:none` semantics.

## Implementation

- `apps/api/app/third_party_api/git/workspace.py`: replace `_ensure_mirror` with `_ensure_ref_cache` keyed by target + ref. The cache directory is `<repos_root>/<target>/<sha256(ref)[:16]>/`, serialized by an in-process lock. For a tag or branch, run `git init --bare` and then `git fetch --no-tags origin <ref>`, retaining that ref's full history and writing the resolved commit to `refs/heads/harness-target` for the local clone; for a full commit, run `git fetch --depth 1 --no-tags origin <sha>`; never run `--mirror`. Rebuild the cache when its origin differs from the current `repo_url`; a failed refresh keeps complete objects, while a failed new cache removes the partial directory.
- `prepare`: the workspace still runs `git clone --no-checkout` from the local cache, then `git switch -c evo/<date>-<runId> <base>` and `remote set-url origin <repo_url>`; the branch/patch/commit/push flow stays unchanged.
- Retry and recovery: when `origin` already has the run branch, a new workspace first fetches `refs/heads/evo/<date>-<runId>` explicitly before `switch --track`; otherwise it creates the branch at `base_commit`. `_push_run_branch` confirms the remote commit exists locally before `merge-base --is-ancestor <remote_commit> HEAD`, fetching the branch first when needed; `push_candidate`'s tag force-with-lease still uses only the expected SHA from `ls-remote`.
- Push policy: keep `HE_GIT_PUSH`; add an optional `HE_GIT_PUSH_URL` (fork / push URL). When configured, every push, pre-push ls-remote, and candidate-tag cleanup uses a separate `push` remote while fetches stay on `origin`; when unset, pushes keep going to `origin`. HTTP(S) push URLs must not embed credentials; credentials come only from the run environment or a credential helper and never enter the repository or database. Third-party targets without write access disable `HE_GIT_PUSH` or configure a writable fork.
- Downstream impact: attribution and clustering finish before `_prepare_workspace` and use Session/attribution caches plus m19 target-content reads, so they do not depend on the run workspace; patch generation writes only files under `sub_dir`, and the full history of the one branch contains the complete tree; evaluation requests use the candidate commit SHA and tree, which do not change with clone depth.
- Run events: the `workspace_prepared` event payload gains `ref`, `cacheHit`, `cloneSeconds`, and `proxyState` (`disabled` / `closed` / `open`), plus a bounded (≤20) `gitOperations` list. Each entry has `operation` (ls-remote / clone / fetch / push), `viaProxy`, `proxyStateBefore` / `proxyStateAfter`, `fallbackReason`, `durationMs`, `exitCode`, and `targetHost`. Full URLs, credentials, stderr, and proxy configuration never appear; truncation is labelled with `gitOperationsTruncated`.
- Proxy observability: every git subprocess emits one structured log `git.proxy.operation` (the same fields, plus `runId` / `jobId` / `stage`; a proxy probe is `operation=probe`, `runId=null`), and log aggregation can filter by runId. A proxy-layer failure followed by a direct retry records `viaProxy=false` and `fallbackReason` (`proxy_connect` / `407` / `tunnel` / `timeout`); health probes are separated from run traffic so a failed probe is never mistaken for a run that skipped the proxy.
- Failure and cleanup: error classes keep the `clone` / `reference` / `workspace` / `subdirectory` / `push` boundaries and never expose stderr or credentials.
- Tests: argv assertions exclude `--mirror`; cover tag, branch, full SHA, cache reuse, changed-ref refresh, missing ref, and failure cleanup; cover prepare → patch → commit → ancestry → push against a local bare remote, the recovery scenario, the push URL, and the event payload.
- Documentation: add a git-workspace page, update deployment configuration and the design-doc sections, add an Agent Note, and record the trade-offs of single-ref cloning, caching, push credentials, and observability.

## Steps

1. Design and implement the target + ref cache and single-ref fetch, with argv, ref-type, cache-hit, and refresh tests.
2. Wire prepare / workspace / push and add commit, ancestry, push, recovery, and failure-cleanup tests.
3. Add ref, cache, duration, proxy state, and `gitOperations` fields to the run event and test the payload.
4. Make the push target and credential configuration explicit, with validation and docs; third-party targets do not push by default.
5. Update the Agent Note and docs, run the gates, and measure one real single-ref clone.

## Dependencies and delivery boundary

- Depends on: m19-01 (single-ref target-content reads).
- Delivery boundary: only the run-workspace clone/cache/push boundary and git observability; no change to the m18 proxy implementation, m19 target-content reads, patch generation, evaluation, frontend, or the `preview/*` contract.
- Old full-mirror cache directories are not migrated; the new layout reads per target + ref, and push credentials never enter the database.

## Independent verification

```sh
pnpm test:api
pnpm typecheck:api
pnpm verify:flow
pnpm lint:docs
```

- Unit tests: a local bare repository's tag, branch, and full SHA each fetch only the target ref; argv contains no `--mirror`; cache reuse does not clone again; a changed ref triggers a fetch; failure classes and cleanup behave as expected; prepare → commit → push succeeds against a local bare remote.
- Proxy observability tests: a healthy proxy records `viaProxy=true`; a proxy-layer failure retried directly records `viaProxy=false` and `fallbackReason`; disabled / open states are recorded; probes are not mixed with run traffic; logs and events contain no credentials or full URLs; `gitOperations` is bounded.
- Recovery scenario: with an existing remote run branch and a new workspace, fetch, switch, merge-base, and a fast-forward push succeed; candidate tag force-with-lease is unaffected; attribution/clustering/patch/evaluation requests are unchanged by the single-ref clone.
- Measurement: `git clone --branch v6.4.1 --single-branch --no-tags https://github.com/obra/superpowers /tmp/sp` has a pack of roughly 3.9MiB and finishes well under 60 seconds; no `--mirror` remains in the run-workspace code path.

## Acceptance

- A cold run-workspace clone no longer runs `--mirror`; tags, branches, and full commits fetch only the target ref.
- A single-ref clone can create the run branch, write a patch, commit, pass ancestry validation, and push; the push target/credential policy is explicit, and third-party targets without write access do not get branches pushed by default.
- The cache hits and refreshes per target + ref; transient failures do not lose complete objects, and partial directories can be retried.
- Any run can answer from its run events or structured logs whether each ls-remote / clone / fetch / push used the proxy, how the proxy state changed, and whether it fell back to direct access and why (proxy_connect / 407 / tunnel / timeout, etc.) without SSH. `gitOperations` is bounded and contains no credentials.
- Existing API, contract, frontend, and evaluation contracts stay unchanged; a target clone finishes within the 60-second bound.
- Retry/recovery: with an existing remote run branch, a new workspace fetches that branch explicitly and continues commit/push; it never fails because the single-ref cache lacks the run branch.
- Attribution, clustering, patch generation, and evaluation commit semantics stay unchanged (only the run-workspace clone path changes).

## Gates and CI

- `pnpm test:api`, `pnpm typecheck:api`, `pnpm lint:api`, `pnpm verify:flow`, `pnpm lint:docs`, `pnpm contract:check`.
- `verify:flow --diff` checks the PR title, each commit's `(#N)`, and scope coverage.
- New tests cover single-ref argv, cache reuse/refresh, ref types, push, event fields, and per-operation proxy records.

## Non-goals

- Do not implement or adjust Xray / VLESS proxying, Secrets, or deployment fallback (m18).
- Do not change the target-content cache or its 20-second bound (m19).
- Do not change attribution / clustering algorithms, patch generation, the evaluation contract, the frontend, the preview contract, or the run's seven-step state machine; do not change proxy selection / circuit-breaking, only add observability.
- Do not store push credentials in the repository or database; do not push branches to third-party public repositories by default.
