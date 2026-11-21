# M25 Multi-host Git push providers

English | [中文](m26-git-push-provider.md)

```yaml flow
kind: milestone
id: m26
title: M26 多托管平台的 Git 推送提供者
status: planned
github:
  number: 36
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/36
```

## Goal

Turn remote writes for evolution runs from "GitHub-specific plus one global URL" into replaceable Git-host providers: a factory selects `GitHubProvider` or `GitLabProvider` from `HE_GIT_PUSH_PROVIDER`; the parent class defines one contract for push, fork, credentials, and remote lookup, while subclasses implement host-specific URLs, APIs, and authentication. A personal PAT is delivered from GitHub Secrets to the server `.env` as `HE_GIT_PUSH_TOKEN`; each target can carry its own push/eval repository; adding a host means adding one subclass without changing the state machine, evaluation, or business flow.

## Scope

The provider abstraction and GitHub/GitLab subclasses in `apps/api/app/third_party_api/git/`; factory wiring in `apps/api/app/config.py` and `main.py`; target/run push and eval target fields plus migrations; Secret injection in `deploy/**` and `.github/workflows/deploy.yml`; target and run-detail status display; related API, contracts, focused tests, documentation, and the Agent Note.

## Acceptance

- Two settings, `HE_GIT_PUSH_PROVIDER` and `HE_GIT_PUSH_TOKEN`, switch between GitHub and GitLab; Deploy writes both into the server `.env` and restarts; a new machine needs only a redeploy, not manual credential setup.
- `GitHubProvider` and `GitLabProvider` implement the same parent contract; adding a host requires one subclass plus a registry entry, with no changes to `GitWorkspaceManager`, candidates, retry, or eval business code.
- Each target can configure its own push/eval repository; prepare, candidate, and final pushes and evaluation reads use the same target, so a read-only upstream can push to a fork and evaluate from that fork.
- The PAT comes only from GitHub Secrets / the server `.env` (0600), never in URLs, the database, events, or logs; missing write access, expiry, or insufficient scope becomes an explicit blocked state with retry.
- Existing single-repository GitHub behavior, APIs, contracts, frontend, and evaluation contracts stay compatible; new tests cover the factory, both subclasses, credential injection, target/run snapshots, and failure retry.

## Non-goals

No interactive OAuth App / GitHub App authorization (a separate follow-up); no automatic PR back to upstream; no per-target provider inside one deployment (the deployment-level `HE_GIT_PUSH_PROVIDER` comes first); no full GitLab CI or other host capabilities, only the extensible provider seam.
