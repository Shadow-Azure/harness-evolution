# Git workspaces and pushes

English | [中文](git-workspace.md)

During prepare, an evolution run builds a local bare cache for the target ref and clones an isolated workspace from it. Target-content reads (`target-content`) and run preparation (`repos`) share one set of cache ownership and self-healing rules. Proxy operations are documented in [Git egress proxy](git-proxy.en.md).

## Cache and clone

- The cache path is `HE_DATA_DIR/repos/<target>/<sha256(ref)[:16]>/` and is keyed by target and normalized ref; an in-process lock plus a cross-process `flock` under the cache root's `.locks/` serializes each path. Target-content reads (`target-content`) share the same ownership rules.
- Tag / branch: run `git init --bare` and then `git fetch --no-tags origin <ref>`, keep that ref's full history, and write the resolved commit to `refs/heads/harness-target` for patches, commits, ancestry checks, and the local clone.
- Full commit: run `git fetch --depth 1 --no-tags origin <sha>` and write `refs/heads/harness-target` as well.
- `--mirror` is never used. A `.state.json` file next to each cache directory records the clone/fetch lifecycle: `incomplete` before, `complete` after success. A cache is deleted and rebuilt when it is `incomplete`, structurally broken, has a different origin, or contains a leftover git lock such as `shallow.lock`; only the matched single ref is affected. A failed refresh keeps a complete cache and restores `complete`; after a `SIGKILL`, the next read rebuilds. A marker-less legacy cache is adopted by writing `complete` when it has no lock and a usable structure.
- While the `flock` is held, git locks inside the cache are removed before a fetch; when git still reports a lock conflict, the lock is cleaned and the fetch retried once, and only a second failure is reported as `cache_stale_lock` (content reads) or a retryable fetch failure (workspace). Before job recovery, startup sweeps both cache roots: it deletes `incomplete` and locked legacy caches and removes leftover locks.
- The workspace is `HE_DATA_DIR/workspaces/<runId>`: run `git clone --no-checkout` from the cache, `remote set-url origin <repo_url>`, then create `evo/<date>-<runId>`. When the remote already has the run branch, fetch it explicitly before `switch --track`; before a push, fetch that branch when the remote commit is missing locally, then run `merge-base --is-ancestor`.

## Push

- `HE_GIT_PUSH` controls every remote write and defaults to true; when false, the candidate is still created locally but is not pushed or evaluated.
- The provider creates the fork; prepare records the derived target on the run snapshot, and eval reuses it. With a token the fork wins, and `HE_GIT_PUSH_URL` is only the no-token fallback; a provider API failure enters `blocked(push)` directly and never falls back silently. Targets do not accept push/eval URLs, and push and eval must point at the same fetchable repository.
- `HE_GIT_PUSH_URL` is an optional global fork / push URL fallback. When set, fetches stay on `origin`, while pushes, candidate-tag `ls-remote`, and deletion use a separate `push` remote; when unset, pushes go to `origin`.
- Credentials come only from the run environment or a credential helper; HTTP(S) URLs must not embed credentials, and neither the repository nor the database stores push credentials.
- Third-party public repositories usually have no write access: disable `HE_GIT_PUSH` or configure a writable fork. A push failure surfaces as `blocked(push)` and is never recorded as a silent success.

## Hosts and credentials

- `HE_GIT_PUSH_PROVIDER=github` (default) or `gitlab` selects a `GitPushProvider` subclass; the factory builds it at startup and rejects unknown values.
- `HE_GIT_PUSH_TOKEN` is a PAT injected only from Secrets or the run environment; `GIT_ASKPASS` uses the provider default username (GitHub `x-access-token`, GitLab `oauth2`) with that token, and the token never enters URLs, the database, events, or logs. The `harness` user has no home, so the script uses an absolute path; with only a token locally, point `GIT_ASKPASS` at the absolute `deploy/git-askpass.sh` path.
- The API base, web root, and git username are derived by the provider subclass from the `repo_url` host (public github.com / gitlab.com use their defaults; self-hosted uses the same host with `/api/v3` or `/api/v4`); special reverse-proxy differences belong in the subclass, not in new environment settings.
- Adding a host means adding one `GitPushProvider` subclass and a registry entry; the prepare / candidate / final state machine, failure classification, and evaluation contract stay unchanged.

## Observability

The `workspace_prepared` event payload records `ref`, `cacheHit`, `cloneSeconds`, `proxyState` (disabled / closed / open), and at most 20 `gitOperations` entries; `gitOperationsTruncated=true` marks truncation. Each entry has operation, viaProxy, proxy states before/after, fallbackReason, durationMs, exitCode, and targetHost.

A lock conflict that survives one retry emits a structured `git.cache.stale_lock` log (cacheKey, repoHost, refHash); a startup sweep that deletes or cleans anything emits `git.cache.sweep`. Neither contains credentials or full stderr.

Every git subprocess also emits one structured `git.proxy.operation` log line with runId, jobId, and stage; a local cache clone makes no network request and records viaProxy=false. a proxy probe is operation=probe with runId=null. A proxy-layer failure retried directly records viaProxy=false and a fallbackReason such as proxy_connect / 407 / tunnel / timeout, with other proxy-layer errors classified as proxy_error. Logs and events contain only the host name, never full URLs, credentials, stderr, or proxy configuration.

Diagnose by reading the `workspace_prepared` payload from `GET /api/evolution/runs/<runId>/events`, or by filtering `git.proxy.operation` logs on runId; no SSH session is required.

## Boundaries

- Old `repos/<targetId>` mirror directories are neither migrated nor read.
- A single-ref cache keeps the full history of that ref; each distinct ref occupies its own directory, so disk use grows with the refs that were visited.
- Workspaces follow the retention policy; repository caches are not removed with workspaces and may need manual cleanup.
- Proxy health probes are recorded separately from run traffic; a failed probe never rewrites a run's viaProxy conclusion.
