# Agent Note: Single-ref shallow target reads

Status: implemented

English | [中文](2026-11-19-single-ref-target-content.md)

## Problem

When the launch wizard resolves a selected version into a body hash, `SubprocessGitContent` first runs `git clone --mirror` on the target repository in the request path and then `git show`s one `SKILL.md` / `AGENT.md`. After the production data-directory migration the cache was empty, and on the mainland-to-GitHub link a full mirror cannot finish within 20 seconds, so users saw "target file read timed out" ([issue #391](https://github.com/Shadow-Azure/harness-evolution/issues/391)). Reading one ref downloaded all history and every ref, wasting transfer and widening the failure window. Egress proxying is orthogonal and belongs to a later independent task (design in [#394](https://github.com/Shadow-Azure/harness-evolution/issues/394)).

## Decision

- Replace the per-repository mirror cache with a per-(`repo_url`, `ref`) shallow repository. The first tag/branch read uses `git clone --depth 1 --single-branch --filter=blob:none --no-checkout --branch <ref>`; a full 40-hex commit uses `git init` plus promisor-remote configuration plus `git fetch --depth 1 --filter=blob:none origin <sha>`. Later reads fetch only the same ref, and `git show` lazily fetches one blob through the promisor remote; `--mirror` is gone.
- The cache key includes the URL and ref, a process-local lock serializes each cache path, and stable classifications cover missing refs/files, network failures, timeouts, missing git, and path traversal. Failures clean partial cache directories.
- Keep the `read_file` interface, the 20-second bound, and body-hash semantics unchanged; no GitHub API, private-repository credentials, or public mirror. Old mirror cache directories stay in place and are not read by the new layout, so no data migration is needed.

## Alternatives considered

- **GitHub Contents API / raw.githubusercontent.com file reads.** Needs a token and quota, and private-repository authorization plus error classification would be separate; it also diverges from the existing git ref semantics (tag/branch/commit), so it is not the primary path.
- **Mirror prewarming or an asynchronous preview.** Prewarming needs a post-deploy background task, and asynchrony would change the synchronous `preview/*` contract and the frontend; both exceed this single-ref fix, and [#391](https://github.com/Shadow-Azure/harness-evolution/issues/391) tracks them separately.
- **Keep the full mirror and only raise the timeout.** The link itself is unstable, so neither transferred bytes nor the failure window shrink; single-ref shallow fetch removes most of the payload.

## Consequences

- A cold read of a new ref still needs the network, but transfers only that ref plus on-demand blobs; tags and branches refresh with one small fetch per read, while full commits reuse the cache.
- Old mirror cache directories are no longer read and are not cleaned automatically; they do not affect the new layout and can be deleted by hand.
- The egress proxy (Secret, Xray deployment, proxy environment, and breaker) is outside this change; proxy failure handling and deployment are a later independent task.
- Callers of `read_file` and the error codes stay unchanged; existing unit tests and cross-stack flows need no contract adjustment.
