# A stale shallow.lock from an interrupted git fetch permanently breaks target content reads and run preparation

English | [中文](bugfix-69-stale-shallow-lock.md)

```yaml flow
kind: issue
id: bugfix-69
milestone: bugfix
depends:
  - m19-01
  - m24-01
priority: P2
status: ready
scope:
  - apps/api/**
  - tests/**
  - docs/**
  - .agents/**
  - plans/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 649
  url: https://github.com/Shadow-Azure/harness-evolution/issues/649
```

## Background

### Problem

Target content reads (m19) and evolution run preparation (m24) both keep shallow git repositories as caches under `HE_DATA_DIR`: `target-content/<repo-url hash>/<ref hash>` for the former and `repos/<target>/<ref hash>` for the latter. Both still run one `git fetch --depth 1` after a cache hit to refresh the ref. If the service is terminated while a fetch or shallow clone is running (deployment restart, job timeout cancellation, process crash, container kill), the `shallow.lock` that git leaves in the cached repository stays behind.

A service restart does not clean that lock: the next read of the same `(repo_url, ref)` fails with `fatal: Unable to create '.../shallow.lock': File exists.` The cache path is stable and the directory is still treated as reusable after the failure, so this is not a one-off: target definition resolution, version reads, and run preparation for a full commit keep failing until a person deletes the cache directory or the lock file.

The frontend maps content-read failures to `repo_unreachable` ("cannot access repository"), reporting the stale lock as a network or permission problem; the workspace side keeps retrying the same poisoned cache as a retryable fetch failure. Neither entry point has a self-healing path.

This analysis had no production logs or on-site evidence, so it cannot confirm whether production has already hit the failure; the conclusion comes from code paths, git source, and reproducible local experiments: the failure mechanism holds, and once it happens it is permanent.

### Impact

- `SubprocessGitContent`: branch and tag reads run `git fetch --depth 1` every time; one stale lock makes that `(repo_url, ref)` cache permanently unreadable, affecting overview target analysis, version resolution, the launch wizard, and target definition freezing.
- `GitWorkspaceManager`: full 40-hex commit refs use `git fetch --depth 1`; if the first fetch is killed before the commit lands, later prepares fail repeatedly. Branch and tag fetches are full-history fetches, and the clone from cache into a workspace creates no shallow boundary, so neither is affected by this lock.
- Both caches live in persistent `HE_DATA_DIR` with no TTL or startup cleanup, so one interruption survives many restarts and affects only the matched target or ref, which makes it easy to misdiagnose as an upstream repository failure.

### Analysis process

First check the git lock lifecycle, then check whether the service keeps reusing the cache after the lock is left behind:

1. Read git v2.50.1 source: `fetch-pack.c` calls `setup_alternate_shallow()` before `get_pack()` (around `fetch-pack.c:1218` on the v0 path and `fetch-pack.c:1563` on the v2 path); `setup_alternate_shallow()` in `shallow.c` creates `<git-dir>/shallow.lock` with `hold_lock_file_for_update()` and only renames it to `shallow` in `commit_shallow_file()`. The lock covers the whole pack transfer and connectivity check; a SIGKILLed process runs no rollback, and git has no lock owner or expiry detection.
2. Reproduced locally with git 2.50.1: create a local remote and a shallow cache, then send SIGKILL to the process group during the fetch's pack phase; `shallow.lock` remains with the new shallow boundary as its content; the next `git fetch --depth 1` exits 128 with `Unable to create ... File exists`; `git cat-file -e` and `git show` for an already cached commit still succeed; removing the lock restores the fetch.
3. Reproduced on the service code path: cold-read a local repository through `SubprocessGitContent.read_file_at_commit`, then write `shallow.lock` into the same cache; the second read raises `GitContentUnavailable("repo_unreachable")`; removing the lock restores it. The service neither self-heals nor avoids reporting a local lock as an unreachable repository.
4. Read the failure handling: `_usable()` in `content.py` checks directory structure only and `_fetch_ref()` raises `repo_unreachable` directly; `_cache_usable()` in `workspace.py` also checks structure only, and `_ensure_ref_cache()` removes the cache only when it was not reusable to begin with, so a reusable poisoned cache is kept; neither path cleans `*.lock`.
5. Read the termination paths: `_run_process()` in `content.py` sends SIGKILL to the process group when a timeout cancels it (`content.py:394`); `_terminate_process_group()` in `workspace.py` sends SIGTERM and then SIGKILL (`workspace.py:1756`, `1769`); the systemd unit uses `KillMode=mixed` with `TimeoutStopSec=45` (`deploy/harness-api.service:24-25`). Every one of these paths can end a git process while it holds the shallow lock.

Reproduction commands and key output (local file remote, git 2.50.1):

```sh
git init --bare cache
git -C cache remote add origin "file:///path/to/remote.git"
git -C cache fetch --depth 1 --no-tags origin refs/heads/main
# SIGKILL the process group during the second fetch's pack phase
ls cache/shallow.lock              # exists
git -C cache fetch --depth 1 --no-tags origin refs/heads/main
# exit 128: fatal: Unable to create '.../shallow.lock': File exists.
rm cache/shallow.lock
git -C cache fetch --depth 1 --no-tags origin refs/heads/main   # recovers
```

### Root cause

- Git's shallow lock is a plain on-disk lock file with no owner, heartbeat, or expiry semantics; an abnormal process exit does not roll it back, and later processes never decide on their own that it is stale.
- The service treats "the directory looks like a repository" as cache usability, never encodes "the previous clone or fetch did not finish" into cache state, and never clears git lock files in a cache this service owns before fetching.
- Failure classification and cache disposition amplify the problem: content reads collapse any fetch failure into `repo_unreachable`, and the workspace keeps a reusable poisoned cache and retries it; neither has a "clean up and retry once or rebuild the cache" self-healing action.
- A first shallow clone is already considered usable by `_usable()` once `.git` exists, so a killed clone is not deleted and rebuilt; instead, fetches continue on an incomplete directory.

## Goals

- After the service is SIGKILLed or restarted, a leftover `shallow.lock` in a cache causes at most one automatic cleanup or rebuild, never a permanent failure.
- The `target-content` and `repos` cache entry points share one ownership, state-validation, and self-healing rule instead of requiring manual directory deletion.
- Failure reasons distinguish "stale cache lock or incomplete cache" from a real unreachable repository, and structured logs or events carry the cache key and host without leaking credentials.
- Cover deployment restarts, job timeout cancellation, process crashes, concurrent reads of the same ref, and cross-process access.

## Design authority

- [07 §5.6 single-iteration execution](../../../plans/fullstack-design/07-backend-implementation.md#56-单轮执行candidate--push--提交评测fullevolutionengineadvance_one_round): the git chain and failure-classification boundary for prepare, candidate, and push.
- [07 §5.8.1 blocked retry policy](../../../plans/fullstack-design/07-backend-implementation.md#581-阻塞重试策略): the existing blocked and retry semantics; this issue only makes cache failures self-healing and does not change the retry semantics of real failures.
- [04 §3 layering and directories](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录): git processes, caching, and host differences stay in `third_party_api` and do not spread into service.
- [docs/git-workspace.md](../../../docs/git-workspace.en.md): the current cache, clone, push, and failure-retention policy; this issue replaces "keep a reusable poisoned cache" with self-healing.
- Git lock implementation: [fetch-pack.c](https://github.com/git/git/blob/v2.50.1/fetch-pack.c#L1218), [shallow.c](https://github.com/git/git/blob/v2.50.1/shallow.c#L386), [lockfile.c](https://github.com/git/git/blob/v2.50.1/lockfile.c).

## Implementation

### 1. Explicit cache ownership: cross-process file lock

- Create a stable lock file under each cache root (for example `<cache_root>/.locks/<key>.lock`) and use `fcntl.flock(LOCK_EX)` to serialize clone, fetch, cleanup, and rebuild for one cache key; keep the lock file outside the cache directory that may be deleted so a rebuild does not invalidate the locked inode.
- The kernel releases flock when a process exits, so there is no need to decide whether a lock belongs to an old process; this closes the gap that the current `asyncio.Lock` is process-local and loses all mutual exclusion after a restart.
- While that flock is held, `shallow.lock` and sibling git lock files inside the cache (`index.lock`, `HEAD.lock`, `config.lock`, `packed-refs.lock`, `refs/**/*.lock`) cannot belong to a live git process of this service, so they can be removed before retrying.

### 2. Cache state and self-healing

- Before a clone or fetch, atomically write an `incomplete` marker (repo_url, ref, start time, fsync); after success, atomically write a `complete` marker (including the resolved commit). A missing or mismatched marker means the cache is not reusable.
- An unusable cache is deleted and rebuilt under the flock. Only the matched single-ref shallow cache is rebuilt, so the cost is bounded and no other ref's cache is touched.
- Caches left by older versions have no marker: when no git lock exists and the structure is usable (`git rev-parse --git-dir` and the origin URL check pass), write `complete` and keep using it, avoiding a full rebuild on upgrade; when a lock file exists, treat the cache as unusable.
- After terminating the process group on a timeout or cancellation, best-effort remove the lock files and mark the cache `incomplete`; even if the process is SIGKILLed afterwards, the already-persisted `incomplete` marker makes the next read rebuild.

### 3. Failure classification and retry

- Recognize git's lock-conflict output (`Unable to create ... shallow.lock`, `Another git process seems to be running`); while holding the flock, clean the lock and retry once, and only then report `repo_unreachable` (content reads) or a retryable fetch failure (workspace).
- A content read exposes no error when the cleanup-and-retry succeeds; on failure, add a stable reason (for example `cache_stale_lock`) and log the cache key, repository host, and ref hash in logs or events, without credentials or full stderr.
- `_ensure_ref_cache()` in the workspace deletes and rebuilds when a lock conflicts or the cache is incomplete, instead of keeping a poisoned cache and retrying it; real network or permission failures keep the existing retry and blocked semantics.

### 4. Startup fallback and documentation

- Before job recovery in the `lifespan`, scan both cache roots: remove leftover git lock files that are no longer held by a flock, and mark caches with an `incomplete` marker for rebuild; no business fetch runs during startup, so the sweep cannot race an active operation.
- Update the cache failure policy in `docs/git-workspace.md` from "keep complete objects" to "a reusable cache must be complete; a poisoned cache is rebuilt", in both Chinese and English.
- Add an Agent Note recording the decision and trade-offs: caches are derived data, lock ownership belongs to OS file locks, and self-healing is preferable to keeping a poisoned cache.

## Implementation steps

1. Add a small shared module for cache directories and lock files in `third_party_api/git/` (cross-process flock, atomic markers, lock-file cleanup), and wire it into the content and workspace call sites first.
2. Rework `SubprocessGitContent`: acquire the flock, validate or rebuild the cache, clean locks before fetch, retry once on failure, and update the failure reason; keep the public interface and timeout budget.
3. Rework `GitWorkspaceManager._ensure_ref_cache()` with the same ownership and self-healing semantics; a failed first fetch of a full commit ref must not keep a poisoned cache.
4. Wire post-timeout and post-cancellation cleanup into `_run_process()` and `_terminate_process_group()`; cleanup failures must not change the original error.
5. Add the startup sweep and connect it to the `main.py` lifespan; finish it before job recovery.
6. Add tests: SIGKILL, stale lock, partial clone, concurrency, and startup sweep; update the m19 and m24 tests and failure-classification assertions.
7. Update `docs/git-workspace.md` and the Agent Note, run docs, flow, and focused API gates, and submit the registration PR and the fix PR.

## Dependencies and boundary

- Dependencies: `m19-01` (single-ref content-read cache) and `m24-01` (single-ref run-workspace cache) are done; this issue only fixes the cache lifecycle and failure path.
- Delivery boundary: do not change the shallow single-ref cache policy, do not introduce a full mirror, do not change the run state machine or the evaluation contract, and add no environment variable or deployment dependency.
- Single-instance deployment is the current premise; flock should still make same-host multi-process access safe, but it does not promise a distributed lock for multiple hosts sharing one `HE_DATA_DIR`.
- Upgrading old caches must be invisible: caches without locks that are structurally usable are reused directly and are not force-rebuilt.

## Verification

```sh
pnpm test:api -- tests/bugfix-69-stale-shallow-lock
pnpm test:api -- tests/m19-01-git-single-ref
pnpm test:api -- tests/m24-01-git-single-ref-workspace
pnpm verify:docs
pnpm verify:flow
```

- Stale lock: after placing a `shallow.lock`, reading the same ref cleans it up and succeeds; assert that `repo_unreachable` is never exposed to the caller.
- SIGKILL: kill the process group during a shallow fetch of a large local pack, read through the same cache from a new process, and assert that the first read rebuilds and succeeds and that no lock file remains after the process exits.
- Partial clone: kill a clone after `.git` is created, then assert that the next read deletes and rebuilds instead of fetching on top of the incomplete directory.
- Concurrency: two processes or two managers read the same cache key at the same time; flock serializes them, only one fetch runs, and both return the same commit.
- Startup sweep: pre-place a leftover lock and an `incomplete` cache, then assert that reads or preparation for the target succeed after startup and that structurally sound old caches are not deleted.
- Real unreachability: a disconnected network or a wrong URL still reports `repo_unreachable` or a retryable fetch failure and is not mistaken for a lock conflict.

## Acceptance

- After a shallow fetch is interrupted by SIGKILL or a deployment restart, the next read or prepare recovers automatically (one rebuild is allowed) without a restart or manual directory deletion.
- Concurrent reads of the same `(repo_url, ref)` do not trample each other during cleanup or rebuild; the cache is always serialized by flock.
- Failure reasons distinguish a stale lock or incomplete cache from a real unreachable repository, and logs or events locate the cache key, host, and ref without credentials.
- Behavior after upgrading old caches is unchanged; caches without locks that are structurally usable are not rebuilt.
- Tests cover both the content-read and run-workspace paths, and the existing m19 and m24 tests do not regress.

## Gates and CI

- `pnpm test:api` (new bugfix-69 tests plus m19 and m24 regressions), `pnpm verify:docs` (bilingual pairing and links), and `pnpm verify:flow` (the issue triplet and status).
- Failure-classification and logging changes in `third_party_api/git` need matching unit tests; without new contract fields there is no contract change.
- CI must run the new tests; real SIGKILL cases use only a local file remote and a temporary directory, with no external network and no production data.

## Non-goals

- Do not switch to a non-shallow full cache, and do not introduce a mirror or a server-side proxy to dodge the lock.
- Do not implement a distributed lock or cache consistency for multiple hosts sharing `HE_DATA_DIR`.
- Do not change the run state machine, the blocked and retry product semantics, or the evaluation contract; only make cache failures at the same stage self-healing.
- Do not clean historical workspaces under `workspaces/` that are unrelated to this lock, and do not change the cache capacity or TTL policy.
