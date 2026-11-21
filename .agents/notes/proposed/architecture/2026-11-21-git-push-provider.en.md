# Agent Note: Multi-host Git push providers

Status: proposed

English | [中文](2026-11-21-git-push-provider.md)

## Problem

Remote writes for evolution runs currently depend on one `GitWorkspaceManager` instance and one global `HE_GIT_PUSH_URL`: prepare, candidate, and final pushes all reuse the same address, and an empty value pushes to the `repo_url` origin. A third-party public upstream without write access must fail with 403 and enter `blocked(push)`, and one global URL cannot route several different upstream repositories. Target/run have no per-target push/eval fields, and evaluation always uses `run.repo_url`; even after moving pushes to a fork, evaluation still fetches the candidate commit from the upstream and defers the failure to eval. Credentials only have the server credential-helper path; the `harness` user is created by bootstrap with `--no-create-home`, so `~/.ssh` and `~/.git-credentials` cannot be assumed.

Production run `01M7VS6587C6DTQ1TBMVH5F05Z` is an instance of this chain: prepare pushed the run branch to the read-only upstream `obra/superpowers` and was rejected, so the run entered blocked; a later manual retry stopped at 6/7 because the retry job was rejected as `RUN_BUSY` by itself. This Note only covers the provider and credential/target abstraction; the retry self-block is a separate defect.

The user chose a personal-account PAT transition and wants only two GitHub Secrets: the type (`HE_GIT_PUSH_PROVIDER`) and the PAT (`HE_GIT_PUSH_TOKEN`). The implementation must use a factory plus parent class and subclasses, so adding a host such as GitLab requires only a new subclass and no business state-machine changes.

## Decision

Add a `GitPushProvider` parent, `GitHubProvider` / `GitLabProvider` subclasses, and `GitPushProviderFactory` under `third_party_api/git/`. The parent defines `remote_url`, `auth_environment`, `ensure_fork`, `open_pull_request`, and the common `push_ref` / `remote_ref`; subclasses implement only host-specific URLs, APIs, fork behavior, and authentication. The factory selects by `HE_GIT_PUSH_PROVIDER` (`github` by default, `gitlab` optional) and rejects unknown values at startup; the provider is built once in the composition root and injected into `GitWorkspaceManager`.

The PAT is delivered from GitHub Secrets into the server `.env` (0600) as `HE_GIT_PUSH_TOKEN`, and Deploy also injects an absolute-path `GIT_ASKPASS` script; git subprocesses read the credential from the environment, and the token never enters URLs, the database, events, or logs. The API base, web root, and git username are derived by the subclass from the `repo_url` host (GitHub: `api.github.com` / `x-access-token`; GitLab: `/api/v4` / `oauth2`; self-hosted uses the same host with `/api/v3` or `/api/v4`); special reverse-proxy or non-standard usernames belong in the subclass, with no new environment settings.

No target push/eval/credential fields are added: the provider creates the fork, prepare records the derived push target in `run.push_repo_url`, falling back to `HE_GIT_PUSH_URL` and `repo_url`, and evaluation reuses the same target. prepare, candidate, and final use the per-run push target so push and eval share one source. `HE_GIT_PUSH` and `HE_GIT_PUSH_URL` stay compatible; one deployment selects one provider, while per-target provider, OAuth/App, automatic PR, and GitLab CI are outside this decision.

## Alternatives considered

- **One global collector repository**: pushes succeed, but evaluation fetches the commit from the target `repoUrl`, and the collector commit is not there; histories, tags, permissions, and audit from different upstreams also mix. Rejected.
- **One deployment per repository**: works today, but N API/DB/upgrade stacks and a fragmented cross-repository view are not a long-term solution. Temporary operations workaround only.
- **OAuth App / GitHub App interactive authorization**: more formal than a PAT, but needs a consent screen, refresh tokens, organization approval, and more code; recorded in the authorization survey and left as a separate follow-up, not bundled with the provider abstraction.
- **A provider type per target**: supports multiple hosts in one deployment but expands configuration and tests; the current need is "change host when changing deployment", so deployment-level `HE_GIT_PUSH_PROVIDER` is enough and per-target stays for later.
- **Continue hard-coding GitHub**: cannot satisfy GitLab or future hosts and leaves the global-URL problem in place.

## Consequences

- Adding a host requires one subclass plus a registry entry; the prepare/candidate/final state machine and evaluation contract stay unchanged.
- Target/run need new-field migrations; old runs and unconfigured fields fall back to current behavior and stay compatible.
- Deploy needs `HE_GIT_PUSH_PROVIDER` and `HE_GIT_PUSH_TOKEN`, plus `GIT_ASKPASS` injection; a new machine only needs a redeploy, not manual credential setup.
- A PAT is still a long-lived personal credential with offboarding, rotation, and audit risk; this Note treats it as a transition, and a dedicated account/App follows in a later slice.
- A fork of a public upstream is still public; sensitive content needs a private mirror.
- GitLab and GitHub differ in fork/API/username fields and must be covered by subclass tests; the provider contract stays minimal so host fields do not leak into business code.
- The retry self-block is outside this decision; it must be fixed separately before rollout, otherwise a failed push can still leave a run in running.
