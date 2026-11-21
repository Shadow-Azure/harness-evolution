# Git workspaces and pushes

English | [中文](git-workspace.md)

During prepare, an evolution run builds a local bare cache for the target ref and clones an isolated workspace from it. Proxy operations are documented in [Git egress proxy](git-proxy.en.md).

## Cache and clone

- The cache path is `HE_DATA_DIR/repos/<target>/<sha256(ref)[:16]>/` and is keyed by target and normalized ref; one in-process lock serializes each path.
- Tag / branch: run `git init --bare` and then `git fetch --no-tags origin <ref>`, keep that ref's full history, and write the resolved commit to `refs/heads/harness-target` for patches, commits, ancestry checks, and the local clone.
- Full commit: run `git fetch --depth 1 --no-tags origin <sha>` and write `refs/heads/harness-target` as well.
- `--mirror` is never used. The cache is rebuilt when its origin differs from the current `repo_url`; a failed refresh keeps complete objects, while a failed first build removes the partial directory so a retry starts clean.
- The workspace is `HE_DATA_DIR/workspaces/<runId>`: run `git clone --no-checkout` from the cache, `remote set-url origin <repo_url>`, then create `evo/<date>-<runId>`. When the remote already has the run branch, fetch it explicitly before `switch --track`; before a push, fetch that branch when the remote commit is missing locally, then run `merge-base --is-ancestor`.

## Push

- `HE_GIT_PUSH` controls every remote write and defaults to true; when false, the candidate is still created locally but is not pushed or evaluated.
- A target/run's `pushRepoUrl` / `evalRepoUrl` selects the write and evaluation target; when both are empty, they fall back to `HE_GIT_PUSH_URL` and then `repoUrl`. Push and eval must point at the same fetchable repository.
- `HE_GIT_PUSH_URL` is an optional global fork / push URL fallback. When set, fetches stay on `origin`, while pushes, candidate-tag `ls-remote`, and deletion use a separate `push` remote; when unset, pushes go to `origin`.
- Credentials come only from the run environment or a credential helper; HTTP(S) URLs must not embed credentials, and neither the repository nor the database stores push credentials.
- Third-party public repositories usually have no write access: disable `HE_GIT_PUSH` or configure a writable fork. A push failure surfaces as `blocked(push)` and is never recorded as a silent success.

## Hosts and credentials

- `HE_GIT_PUSH_PROVIDER=github` (default) or `gitlab` selects a `GitPushProvider` subclass; the factory builds it at startup and rejects unknown values.
- `HE_GIT_PUSH_TOKEN` is a PAT injected only from Secrets or the run environment; a `GIT_ASKPASS` script reads `HE_GIT_PUSH_USERNAME` / `HE_GIT_PUSH_TOKEN`, and the token never enters URLs, the database, events, or logs. The `harness` user has no home, so the script uses an absolute path.
- Optional `HE_GIT_PUSH_API_URL` / `HE_GIT_PUSH_BASE_URL` / `HE_GIT_PUSH_USERNAME` override self-hosted or enterprise hosts; defaults come from the provider (GitHub: `api.github.com` / `x-access-token`; GitLab: `/api/v4` / `oauth2`).
- Adding a host means adding one `GitPushProvider` subclass and a registry entry; the prepare / candidate / final state machine, failure classification, and evaluation contract stay unchanged.

## Observability

The `workspace_prepared` event payload records `ref`, `cacheHit`, `cloneSeconds`, `proxyState` (disabled / closed / open), and at most 20 `gitOperations` entries; `gitOperationsTruncated=true` marks truncation. Each entry has operation, viaProxy, proxy states before/after, fallbackReason, durationMs, exitCode, and targetHost.

Every git subprocess also emits one structured `git.proxy.operation` log line with runId, jobId, and stage; a local cache clone makes no network request and records viaProxy=false. a proxy probe is operation=probe with runId=null. A proxy-layer failure retried directly records viaProxy=false and a fallbackReason such as proxy_connect / 407 / tunnel / timeout, with other proxy-layer errors classified as proxy_error. Logs and events contain only the host name, never full URLs, credentials, stderr, or proxy configuration.

Diagnose by reading the `workspace_prepared` payload from `GET /api/evolution/runs/<runId>/events`, or by filtering `git.proxy.operation` logs on runId; no SSH session is required.

## Boundaries

- Old `repos/<targetId>` mirror directories are neither migrated nor read.
- A single-ref cache keeps the full history of that ref; each distinct ref occupies its own directory, so disk use grows with the refs that were visited.
- Workspaces follow the retention policy; repository caches are not removed with workspaces and may need manual cleanup.
- Proxy health probes are recorded separately from run traffic; a failed probe never rewrites a run's viaProxy conclusion.
