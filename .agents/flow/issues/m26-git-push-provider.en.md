# Multi-host Git push providers: PAT/Secrets with a factory and subclasses

English | [中文](m26-git-push-provider.md)

```yaml flow
kind: issue
id: m26-01
milestone: m26
depends:
  - m24-01
  - m5-09
  - m5-11
priority: P1
status: backlog
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - deploy/**
  - .github/workflows/**
  - docs/**
  - plans/**
  - .agents/**
  - scripts/**
adr: []
github:
  number: 457
  url: https://github.com/Shadow-Azure/harness-evolution/issues/457
```

## Background

Production run `01M7VS6587C6DTQ1TBMVH5F05Z` (2026-11-20, target `skill:systematic-debugging@v6.4.1`, upstream `https://github.com/obra/superpowers`) pushed its run branch to a read-only third-party upstream during prepare. The remote rejected the push, and the run ended with `blocked(push)` and `run branch publication failed`. A later manual retry cleared the blocked state back to running, but the retry job submitted a follow-up `evolution_prepare` while it was itself still active; the same-ref active-job deduplication classified it as `RUN_BUSY` and swallowed the error. The run stopped at step 6/7 with zero rounds and no follow-up job, becoming a zombie.

The incident is not a single point failure. `GitWorkspaceManager` currently fixes one global `push_url` (from `HE_GIT_PUSH_URL`) at construction time, and prepare, candidate, and final pushes all reuse it. With an empty `HE_GIT_PUSH_URL` the manager pushes to `origin`, which must fail with 403 for a third-party public repository without write access. At the same time, evaluation always uses `run.repo_url` plus the candidate commit (`eval_poller.py:92-99`, `eval_gateway/mapper.py:45`). Even after moving pushes to a fork, evaluation would still fetch the commit from the upstream, turning `blocked(push)` into `blocked(eval)`. Target and run have no per-target push/eval fields, so multiple repositories cannot be routed through one global URL. There is no `GIT_ASKPASS` / PAT injection path, and the `harness` user is created by bootstrap with `--no-create-home`, so `~/.ssh` and `~/.git-credentials` cannot be assumed.

The user has chosen a **personal-account PAT** transition: two GitHub Secrets, one for the provider type (for example `HE_GIT_PUSH_PROVIDER=github`) and one for the PAT (`HE_GIT_PUSH_TOKEN`); Deploy writes both into the server `.env` and restarts; the implementation uses a **factory plus parent class and subclasses**, where the parent owns the public contract and host-specific behavior lives in subclasses. GitHub is first; when the deployment moves to another environment such as GitLab, URLs, APIs, and authentication change and only a new subclass should be required, without changing the business state machine. This also covers multi-repository forks, evaluation from the same target, PAT/Secrets delivery, and extensibility, so it fits one independently verifiable vertical slice.

A related but separate defect should be recorded: a retry job is rejected as `RUN_BUSY` by its own active job when it schedules the next stage. It is not part of the provider abstraction, but it must be fixed separately before rollout; this issue's verification does not depend on automatic retry and only verifies that a failed push enters blocked and can be retried after the credential is fixed.

## Goals

- Switch between GitHub and GitLab with two core settings, `HE_GIT_PUSH_PROVIDER` and `HE_GIT_PUSH_TOKEN`: the type accepts `github` and `gitlab`; the PAT is injected from GitHub Secrets into the server `.env`; a new machine only needs a redeploy, not manual credential setup.
- Introduce a `GitPushProvider` parent class (common public contract and common git execution) and `GitHubProvider` / `GitLabProvider` subclasses. The factory instantiates the subclass selected by `.env`; adding a host requires one subclass plus a registry entry, with no changes to `GitWorkspaceManager`, candidates, retry, or eval business code.
- prepare, candidate, and final use the same per-run push target; evaluation uses the same per-run eval target. A target can configure `pushRepoUrl` / `evalRepoUrl`; empty values derive a fork from the provider or fall back to `repoUrl`.
- A read-only third-party upstream can push to a writable fork (personal PAT now, machine account later) and be evaluated from that fork, instead of deferring the failure to eval.
- PAT/credentials come only from Secrets or the server `.env` (0600), never from URLs, the database, events, or logs. Push failures, expired tokens, and insufficient scope become explicit blocked states with retry.
- Keep the existing single-repository GitHub behavior and the API, contract, frontend, and evaluation contracts compatible; add tests for the factory, both subclasses, credentials, target/run snapshots, and failure retry.

## Design authority

- [04 §3 Layering and directories](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录): keep git processes and host differences in `third_party_api`, and business state machines in `service`.
- [04 §9 Configuration inventory](../../../plans/fullstack-design/04-backend-architecture.md#9-配置项清单): ownership and defaults for `HE_GIT_PUSH`, `HE_GIT_PUSH_URL`, and related git settings.
- [07 §5.6 Git chain](../../../plans/fullstack-design/07-backend-implementation.md): push semantics and failure classification across prepare, candidate, accept, and final.
- [docs/git-workspace.md](../../../docs/git-workspace.en.md): the current workspace, cache, push-remote, and credential policy.
- [m24-01 #411](https://github.com/Shadow-Azure/harness-evolution/issues/411): the previous single-ref workspace and push-target/observability slice.
- [m5-09 #58](https://github.com/Shadow-Azure/harness-evolution/issues/58): existing candidate commit/ref, push retry, and acceptance contract.
- [m5-11 #60](https://github.com/Shadow-Azure/harness-evolution/issues/60): blocked recovery and backoff; this issue only guarantees push failures enter blocked and does not change its scheduling defect.
- GitHub REST: [Create a fork](https://docs.github.com/en/rest/repos/forks), [PAT authentication](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
- GitLab Docs: [Fork a project](https://docs.gitlab.com/ee/api/projects.html#fork-project), [Personal access tokens](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html), [Git over HTTPS](https://docs.gitlab.com/ee/gitlab-basics/start-using-git.html).

## Implementation

### 1. Configuration and factory

- Add to `Settings`:
  - `git_push_provider: Literal["github", "gitlab"] = "github"` from `HE_GIT_PUSH_PROVIDER`; unknown values fail startup with `ConfigError` instead of silently falling back.
  - `git_push_token: SecretStr | None` from `HE_GIT_PUSH_TOKEN`; an empty value keeps the existing credential-helper behavior.
  - Optional `git_push_api_url`, `git_push_base_url`, and `git_push_username` for self-hosted/enterprise hosts; defaults come from the subclass and values must be HTTP(S), credential-free, and have no query or fragment.
  - Keep `HE_GIT_PUSH` (master switch) and `HE_GIT_PUSH_URL` (legacy global fallback) so current deployments do not break.
- `GitPushProviderFactory.create(settings)` selects from `{"github": GitHubProvider, "gitlab": GitLabProvider}`. The provider is built once in the composition root and injected into `GitWorkspaceManager`; it does not read the environment per run.
- The factory only selects an implementation; business code depends on the parent interface and never imports a concrete subclass.

### 2. Parent class and subclasses

```python
class GitPushProvider(ABC):
    provider_id: str

    @abstractmethod
    def remote_url(self, repo_url: str, *, fork: bool = False) -> str:
        """Return a pushable HTTPS/SSH URL with no credentials."""

    @abstractmethod
    def auth_environment(self) -> Mapping[str, str]:
        """Return GIT_ASKPASS / GIT_SSH_COMMAND / GIT_CONFIG_* without logging secrets."""

    @abstractmethod
    async def ensure_fork(self, upstream_url: str, owner: str | None = None) -> str:
        """Find or create a fork under owner and return its URL."""

    @abstractmethod
    async def open_pull_request(self, fork_url: str, upstream_url: str, branch: str, title: str) -> str | None:
        """Optional capability; return None when unsupported."""

    # Common git execution template methods: push / ls-remote / delete ref
    async def push_ref(self, workspace: Path, remote_url: str, refspec: str) -> None: ...
    async def remote_ref(self, workspace: Path, remote_url: str, ref: str) -> str | None: ...
```

- `GitHubProvider`: default `https://github.com` and `https://api.github.com`; `GET /user` for the login; `GET /repos/{owner}/{repo}` for existence; `POST /repos/{owner}/{repo}/forks` to fork; HTTPS username `x-access-token` and password `HE_GIT_PUSH_TOKEN`; API header `Authorization: Bearer`.
- `GitLabProvider`: default `https://gitlab.com` and `https://gitlab.com/api/v4`; `GET /user` for the username; URL-encode the project path as `owner%2Frepo`; `POST /projects/{encoded}/fork` (optionally with `namespace_path`); HTTPS username `oauth2` and password PAT; API header `PRIVATE-TOKEN`; self-hosted hosts use `HE_GIT_PUSH_API_URL` / `HE_GIT_PUSH_BASE_URL`.
- Common git execution stays in the parent (`git push`, `git ls-remote`, ref deletion); all host differences (URL, authentication, fork, PR) stay in subclasses. Adding `GiteaProvider` means one subclass plus a registry entry, with no business changes.
- Remote ref lookup keeps using `git ls-remote`, not host-specific branch/tag semantics; candidate tags keep their expected-SHA force-with-lease behavior.

### 3. GitWorkspaceManager and per-run targets

- `GitWorkspaceManager` no longer stores a single `_push_url`. `prepare` resolves the push URL from `run.push_repo_url`, the provider-derived fork, `HE_GIT_PUSH_URL`, then `run.repo_url`; `push_candidate` and `publish_run_branch` receive the run or an explicit push URL and never read mutable global state.
- Authentication: a `GIT_ASKPASS` script returns `HE_GIT_PUSH_USERNAME` / `HE_GIT_PUSH_TOKEN`; the provider's `auth_environment` injects it into git subprocesses. Tokens never enter URLs; logs and events record only host and ref, not tokens.
- Push failures still go through `classify_git_failure` to `blocked(push)`; retry semantics are unchanged. This issue does not fix the retry self-block.
- Evaluation: `evalRepoUrl = run.eval_repo_url or run.push_repo_url or run.repo_url`; `EvalRequest.repo_url` uses it so push and eval share one source.

### 4. Target/run data and migration

- `evolution_targets` gains `push_repo_url` (empty = derive), `eval_repo_url` (empty = same as push), and `push_credential_ref` (empty = global `HE_GIT_PUSH_TOKEN`; reserved for per-target credentials).
- `evolution_runs` snapshots the same values; `LaunchService._run_values` writes them; historical rows default to empty strings.
- Target API/contracts/UI add the fields and validation: URLs must not embed credentials; the provider remains deployment-level in this issue and is not selectable per target.
- UI: target list/detail show provider, push/eval URLs, and PAT status (configured / missing / expired) with a "configure PAT" explanation when missing; run detail shows push/eval targets and the blocked reason. Full automatic fork provisioning/authorization status can be a follow-up, but the fields and read-only display land here.

### 5. Deploy and Secrets

- Add to the `production` Environment:
  - `HE_GIT_PUSH_PROVIDER=github` (type; secret or variable).
  - `HE_GIT_PUSH_TOKEN=<PAT>` (Secret; fine-grained or classic `public_repo`).
  - Optional `HE_GIT_PUSH_API_URL`, `HE_GIT_PUSH_BASE_URL`, and `HE_GIT_PUSH_USERNAME` for self-hosted/enterprise hosts.
- The Deploy "inject deployment configuration" step writes these values into `/opt/harness/shared/.env` (0600) using the existing base64 + `inject-config.py` pattern, and injects:
  - `GIT_ASKPASS=/opt/harness/shared/git-askpass.sh` (0755; the script reads env and stores no token).
- Restart `harness-api`. The `harness` user has no home, so credentials use absolute paths and never rely on `~/.ssh` or `~/.git-credentials`.
- New machine: the same Deploy delivers the Secrets automatically; only MySQL and `HE_DATA_DIR` data need migration.

### 6. Security

- Tokens live only in GitHub Secrets and the server's 0600 `.env`; never in URLs, the database, events, or logs; use `SecretStr` and the shared redaction helper.
- Least-privilege PAT: GitHub fine-grained `Contents: R/W`, `Metadata: R`; fork creation needs `Administration: R/W` or `Repository creation: R/W` (or a classic `public_repo` fallback); GitLab uses the minimal `api` / `write_repository` scope.
- A fork of a public upstream is public; target preparation must say so, and sensitive content should use a private mirror.
- A personal PAT is transitional: offboarding, rotation, and audit risk are reduced later by a dedicated account/GitHub App; this issue does not implement App/OAuth.

## Implementation steps

1. Add `HE_GIT_PUSH_PROVIDER` / `HE_GIT_PUSH_TOKEN` / optional URL settings and validation; implement the `GitPushProvider` parent, `GitHubProvider`, and `GitPushProviderFactory`; add factory and configuration tests.
2. Implement `GitLabProvider` (fork, API base, `oauth2` authentication, URL encoding); cover it with local mock HTTP / local bare remotes; add self-hosted URL tests.
3. Refactor the `GitWorkspaceManager` push path: resolve the per-run push URL, inject provider authentication, remove mutable global state from `push_candidate` / `publish_run_branch`; add prepare/candidate/final local bare-remote tests.
4. Add `push_repo_url` / `eval_repo_url` / `push_credential_ref` to target/run with migrations; snapshot them in `LaunchService`; make `eval_poller` use the eval target; add API/contract tests.
5. Inject the two core settings and `GIT_ASKPASS` in Deploy; document PAT creation, rotation, machine replacement, and adding a new host.
6. Add target/run UI fields and status; add frontend tests; run the full gates.
7. Add an Agent Note describing the provider seam, configuration, credentials, and how to add a host.

## Dependencies and boundary

- Depends on m24-01 (single-ref workspace and push target), m5-09 (candidate commit/ref/push), and m5-11 (blocked recovery).
- Boundary: only the Git push provider abstraction, PAT/Secrets delivery, target/run push/eval targets, and minimal UI status. No interactive OAuth/App authorization, automatic PR, per-target provider, GitLab CI, or full automatic fork provisioning.
- Keep `HE_GIT_PUSH` / `HE_GIT_PUSH_URL` compatible; behavior stays unchanged when the new fields are absent.
- The retry self-block is a separate defect. This issue does not change its scheduling; it must be fixed separately before rollout, otherwise a failed push can still leave a run in running.

## Verification

```sh
pnpm test:api
pnpm test:web
pnpm typecheck:api
pnpm typecheck:web
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
pnpm test:gates
```

- Factory: `HE_GIT_PUSH_PROVIDER=github` yields `GitHubProvider`, `gitlab` yields `GitLabProvider`, and an unknown value fails startup; a new test subclass selected only by a registry entry works without business changes.
- GitHub: local bare remote plus mock/real fork URL; prepare/candidate/final push to the per-run fork; the token is injected through `GIT_ASKPASS`; URLs, events, and logs never contain the token.
- GitLab: local bare remote plus a mock API; `POST /projects/{encoded}/fork`, `PRIVATE-TOKEN`, the `oauth2` username, and a self-hosted API base are covered; push/eval URLs are correct.
- Target/run: `push_repo_url` / `eval_repo_url` snapshots; eval uses the eval target; historical runs fall back to `repo_url`; rows are readable before and after the migration.
- Failures: push 403/401/expiry enter `blocked(push)` with a locating message; after fixing the credential, retrying the current stage does not rerun iterations.
- Regression: GitHub single-repository behavior without the new fields matches existing tests; `HE_GIT_PUSH=false` still skips push and evaluation.

## Acceptance

- The two core settings, `HE_GIT_PUSH_PROVIDER` and `HE_GIT_PUSH_TOKEN`, switch between GitHub and GitLab; Deploy writes `.env` and restarts, and a new machine only needs a redeploy.
- The `GitPushProvider` parent defines the common contract; `GitHubProvider` / `GitLabProvider` implement host differences; adding a host needs only a subclass plus a registry entry, with no business state-machine changes.
- prepare / candidate / final use the per-run push target; evaluation uses the per-run eval target; a read-only upstream can push to a fork and be evaluated from that fork.
- The PAT never enters URLs, the database, events, or logs; missing/expired/insufficient scope becomes an explicit blocked state with retry.
- Target/run API, contracts, UI, and migrations are complete; historical runs stay compatible; existing GitHub single-repository behavior does not regress.
- Documentation, the Agent Note, tests, and gates are complete; `pnpm verify:flow` is green.

## Gates and CI

- `pnpm test:api`, `pnpm test:web`, `pnpm typecheck`, `pnpm contract:check`, `pnpm verify:flow`, `pnpm lint:docs`, `pnpm test:gates`.
- `verify:flow --diff` validates the PR title, commit `(#N)` markers, and scope coverage.
- New tests cover the factory, both subclasses, the authentication environment, forks, per-run push/eval, migrations, and failure retry; credential redaction is asserted.

## Non-goals

- No interactive GitHub App / OAuth App authorization (a separate follow-up); no organization approval or SSO here.
- No automatic PR back to upstream or automatic GitLab MR creation; `open_pull_request` is only an interface placeholder.
- No per-target provider inside one deployment; the deployment-level `HE_GIT_PUSH_PROVIDER` selects the provider.
- No GitLab CI or full Gitea and other host capabilities; only the subclass extension path is verified.
- No fix for the retry self-block and no change to blocked backoff; credentials never enter the repository, database, or URLs.
