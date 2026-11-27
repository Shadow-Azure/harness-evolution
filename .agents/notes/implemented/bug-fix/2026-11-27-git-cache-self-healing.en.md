# Agent Note: Git caches self-heal through file locks and lifecycle markers

Status: implemented

English | [中文](2026-11-27-git-cache-self-healing.md)

## Problem

Target-content reads (`target-content`) and run preparation (`repos`) both treat a single-ref shallow repository as a persistent cache under `HE_DATA_DIR` and run `git fetch` to refresh it after a hit. git's `shallow.lock` is a plain on-disk lock: it is held for the whole pack transfer of a fetch, it has no owner or expiry, and a SIGKILL or deployment restart never rolls it back. The service used to judge a cache only by its directory structure, while the in-process `asyncio.Lock` stops providing mutual exclusion across a restart. One interruption therefore made the same `(repo_url, ref)` fail forever until a person deleted the lock or cache directory; content reads also reported that local failure as `repo_unreachable`, and the workspace kept retrying the same broken cache.

## Decision

- Add `third_party_api/git/cache.py` so both cache entry points share one ownership and lifecycle policy instead of growing separate cleanup logic.
- Serialize clone, fetch, cleanup, and rebuild for each cache key with `fcntl.flock(LOCK_EX)` on a lock file under the cache root's `.locks/`; the lock file lives outside the cache directory that a rebuild deletes. The kernel releases the lock when the process dies, so the service never has to decide whether a lock belongs to an old process.
- Keep `<ref-key>.state.json` next to each cache directory: write `incomplete` atomically before a clone or fetch (with repo_url, ref, start time, and an fsync), then `complete` with the resolved commit after success. The marker sits outside the directory because `git clone` requires an empty destination.
- After a hit, remove `shallow.lock`, `index.lock`, `HEAD.lock`, `config.lock`, `packed-refs.lock`, and `refs/**/*.lock` inside the held flock before fetching. When git still reports a lock conflict, clean and retry once; only a second failure is reported as the new `cache_stale_lock` (content reads) or a retryable fetch failure (workspace), with a structured log carrying cacheKey, repoHost, and refHash.
- Delete and rebuild a cache that is `incomplete`, structurally broken, has a different origin, or contains a git lock. A failed refresh keeps a complete cache and restores `complete`; an `incomplete` left by SIGKILL triggers one rebuild on the next read.
- Adopt a marker-less legacy cache by writing `complete` when it has no git lock and a usable structure, so an upgrade does not rebuild everything. A locked legacy cache is treated as unusable.
- Before job recovery, startup sweeps both cache roots: it deletes `incomplete` caches and locked legacy caches and removes leftover locks no longer held by a `flock`, while structurally healthy legacy caches stay untouched.

## Alternatives considered

- **Delete git locks unconditionally before every fetch without a cross-process lock**: this removes a live lock while another process is fetching and corrupts the cache through concurrent writes. Rejected.
- **Put the cross-process lock file inside the cache directory**: a rebuild deletes the directory, waiters keep a lock on an invalidated inode, and a new process can create a new lock and enter concurrently. Rejected.
- **Delete and rebuild on every fetch failure**: one network blip would discard complete objects and amplify rebuild cost, violating the rule that real failures keep the existing retry semantics. Rejected.
- **Rely only on the in-process `asyncio.Lock`**: restarts and multiple processes lose mutual exclusion, which is half of this bug. Rejected.
- **Write the state marker inside the cache directory**: `git clone` refuses a non-empty destination, so the first clone fails. Rejected.
- **Delete every marker-less legacy cache at startup**: an upgrade would force a full rebuild, violating the seamless-upgrade requirement. Rejected.

## Consequences

- Every cache operation adds two atomic file writes and one `flock`; reads for the same cache key were already serialized, so bounded waiting is acceptable.
- Reusability is now decided by the marker and git locks rather than directory structure alone; rebuilding a broken cache is limited to one ref.
- Content reads gain the stable `cache_stale_lock` reason, and run logs gain `git.cache.stale_lock` and `git.cache.sweep` events.
- Only same-machine multi-process safety is promised; distributed locking or cache consistency across hosts sharing `HE_DATA_DIR` is out of scope.
- The flock covers service processes only. When the API is SIGKILLed, a git child started in its own session can briefly survive, leaving a narrow race between the next process cleaning the stale lock and that orphan writer. Graceful shutdown kills the process group; this window is accepted rather than adding a process-level cleanup protocol.
- Tests cover leftover locks, half-built caches, legacy caches, concurrency, startup sweep, and SIGKILL releasing the flock; the existing m19 and m24 cache semantics keep passing.
