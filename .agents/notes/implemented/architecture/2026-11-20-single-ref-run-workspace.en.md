# Agent Note: Single-ref evolution run workspaces and per-operation observability

Status: implemented

English | [中文](2026-11-20-single-ref-run-workspace.md)

## Problem

The evolution prepare workspace cache used to run `git clone --mirror` against the target repository. A full mirror of the target `obra/superpowers@v6.4.1` measured 290MB, and cross-border links repeatedly failed within the fixed 60-second bound; the half-finished mirror was then deleted, so retries started from zero. All history of the one relevant branch is about 7.1MB, so downloading every ref to read one ref was the root of the failure window. Separately, proxy state lived only in an in-process circuit breaker, so no one could answer which step of a run used the proxy or when it fell back to direct access.

## Decision

The run-workspace cache becomes a bare repository per target + ref at `data/repos/<target>/<sha256(ref)[:16]>/`, with one in-process lock serializing each path. A tag or branch uses `git fetch --no-tags origin <ref>`, keeps that ref's full history, and writes the resolved commit to the clone-visible `refs/heads/harness-target`; a full commit uses `--depth 1` and writes the same local ref, because a local clone copies only advertised refs. The workspace still runs `git clone --no-checkout` from the cache and then creates `evo/<date>-<runId>`, while fetches stay on `origin`. The cache is rebuilt when its origin differs from the current `repo_url`; a failed refresh keeps complete objects, and a failed first build removes the partial directory.

A single-ref cache does not contain the run branch. When `origin` already has the run branch, a new workspace fetches that branch explicitly before `switch --track`; before a push, when the remote commit is missing locally, it fetches the branch and only then runs `merge-base --is-ancestor`. Recovery therefore does not depend on the cache happening to contain the run branch, and a missing object is not mistaken for a non-fast-forward.

Pushes keep the `HE_GIT_PUSH` master switch and add an optional `HE_GIT_PUSH_URL`. When configured, fetches stay on `origin`, while pushes, candidate-tag `ls-remote`, and deletion use a separate `push` remote; when unset, pushes keep going to `origin`. HTTP(S) URLs reject embedded credentials, credentials come only from the run environment or a credential helper, third-party read-only targets disable pushes or configure a writable fork, and a push failure surfaces as `blocked(push)`.

Observability has two layers. At the process layer, every git subprocess emits a structured `git.proxy.operation` log with operation, viaProxy, proxy states before/after, fallbackReason, durationMs, exitCode, targetHost, and runId / jobId / stage; a proxy probe is operation=probe with runId=null so health probes never mix with run traffic. At the run layer, a contextvar collects network operations during prepare into a bounded (20-entry) list projected onto the `workspace_prepared` event as `ref`, `cacheHit`, `cloneSeconds`, `proxyState`, and `gitOperations`; `gitOperationsTruncated` marks truncation. Records contain only the host name, never full URLs, credentials, stderr, or proxy configuration.

## Alternatives considered

- **Keep the mirror and make only the clone shallow.** Rejected: a mirror means every ref, and a shallow mirror still handles shallow history for every ref, so "read one ref" cannot become the cache key.
- **Run `git clone --single-branch` directly into each workspace without a cache.** Rejected: repeated runs of the same target + ref would download the same 7MB history every time, while cache hits and explicit refresh are acceptance criteria of this issue.
- **Reuse the m19 target-content cache.** Rejected: the m19 cache uses `--filter=blob:none` for read-only file content, while a run workspace needs complete trees/commits and its own run branch; sharing would couple two lifecycles and cleanup policies.
- **Embed credentials directly in the push URL.** Rejected: the URL would reach git config, caches, and error contexts, violating the boundary that credentials never enter the repository or database.
- **Replace run events with an admin-only read endpoint.** Rejected: events are persisted per run and naturally carry authorization and history; an extra endpoint adds no information this issue needs while widening the API contract.
- **Expose half_open verbatim in events.** Rejected: the event contract exposes only disabled / closed / open; half_open still routes through the proxy and is projected as closed, while the half-open state remains in `git.proxy.state` logs.

## Consequences

Cache disk use grows with the visited target + ref pairs; workspace retention does not clean repository caches, so they may need manual removal, and old full-mirror directories are neither migrated nor read. A branch cache performs one ref fetch per prepare to discover a new commit, while a full-SHA hit goes back online only when the commit is missing. Recovery adds one run-branch fetch, buying determinism for the single-ref cache and fast-forward checks. `gitOperations` keeps only ls-remote / clone / fetch / push; other local git subprocesses still emit structured logs but stay out of the event list. A failed proxy probe never rewrites a run's viaProxy conclusion, and redaction relies on the shared sanitizer plus host-only extraction.
