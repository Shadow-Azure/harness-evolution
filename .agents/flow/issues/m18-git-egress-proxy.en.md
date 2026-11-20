# Production git egress proxy: Xray/VLESS config, secret injection, and health fallback

English | [中文](m18-git-egress-proxy.md)

```yaml flow
kind: issue
id: m18-01
milestone: m18
depends: []
priority: P1
status: in-progress
scope:
  - apps/api/**
  - deploy/**
  - .github/workflows/deploy.yml
  - docs/**
  - .agents/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - README.md
  - README.en.md
  - README.i18n.yaml
adr: []
github:
  number: 397
  url: https://github.com/Shadow-Azure/harness-evolution/issues/397
```

## Background

When production reads a target repository's `SKILL.md` / `AGENT.md`, a cold cache triggers git operations against GitHub; on mainland links this often cannot finish within 20 seconds, which the front end shows as "target file read timed out" ([issue #391](https://github.com/Shadow-Azure/harness-evolution/issues/391)). Single-ref shallow fetch reduces the payload, but it does not fix unstable egress; an optional proxy is needed at the git-subprocess layer, and a failed proxy must not take down the API or in-flight evolution jobs.

VLESS is an Xray outbound protocol, not an HTTP proxy, so it cannot be placed directly in `HTTPS_PROXY`; production needs a resident local Xray client that turns the VLESS outbound into a mixed/HTTP inbound on `127.0.0.1`. Proxy credentials live only in the GitHub Secret and a server-local config file; the API receives only a credential-free local address.

## Goals

- Add one GitHub Environment Secret, `XRAY_CONFIG`, holding the complete Xray JSON; deploy renders it into a server-local config file that never enters the repository, the API `.env`, logs, or the PR.
- The deploy pipeline downloads a pinned Xray binary with a pinned checksum on the runner; the server only installs the binary, config, and systemd unit, and the proxy listens on loopback only.
- The API injects `HE_GIT_PROXY` only into git subprocesses, covering target content reads, `ls-remote`, and workspace clone/push, never a global `HTTP_PROXY`/`HTTPS_PROXY`.
- An in-process health state machine opens the circuit to direct access after consecutive proxy-layer failures and returns to the proxy after background probes recover; one proxy-layer failure retries that request directly without restarting the API.
- When the Secret is missing, the JSON is invalid, the proxy fails to start, or a tunnel probe fails, deploy removes `HE_GIT_PROXY` and both the release and git operations return fully to direct access.

## Design authority

- [01 §2 Composition and layering](../../../plans/fullstack-design/01-architecture.md#2-组成与分层): git reads belong to the outbound-integration boundary, and the proxy must not become a global network switch.
- [04 §3 Layering and directories](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录): `third_party_api` isolates git processes and business rules stay in the service layer.
- [04 §9 Configuration inventory](../../../plans/fullstack-design/04-backend-architecture.md#9-配置项清单): `HE_GIT_PROXY` is the only new API setting, and it carries a local proxy address only.
- [issue #394](https://github.com/Shadow-Azure/harness-evolution/issues/394): one Secret, git-only wiring, health circuit breaker, direct fallback, and the failure matrix.

## Implementation

- `apps/api/app/third_party_api/git/proxy.py` provides the proxy controller: `closed` uses the proxy, consecutive failures enter `open` (direct), a cooldown moves to `half_open` probing, and consecutive successes recover; probes use a local HTTP CONNECT to `api.github.com:443` with a 5-second bound.
- `main.py` injects the proxy-aware runner into `SubprocessGitContent`, `SubprocessGitRemote`, and `GitWorkspaceManager`; when the proxy is used the runner sets `HTTPS_PROXY`/`HTTP_PROXY` and rewrites GitHub SSH remotes to HTTPS, when direct it removes those variables, and failures that do not match the proxy layer do not trip the breaker.
- `config.py` adds `HE_GIT_PROXY`, the probe interval, and the probe timeout; production defaults to empty, an invalid value fails startup, and the `main.py` lifespan starts and stops background probing.
- `deploy/` adds the Xray binary fetch script, the config writer, and `harness-proxy.service`; bootstrap idempotently installs the unit and narrows sudo, while `deploy.yml` parses the Secret, downloads and uploads the binary, writes config, restarts the proxy, and injects `HE_GIT_PROXY` only after a successful probe, otherwise unsetting it.
- `docs/git-proxy.md` records the Secret shape, key fields and a placeholder example, first enablement, rotation, rollback, limits, and troubleshooting; `deploy/env.production.example` and the design docs carry `HE_GIT_PROXY` in sync.

## Implementation steps

1. Create the m18 flow files and issue.
2. Implement the proxy controller, runner, configuration, and lifespan wiring, with unit tests.
3. Implement the deploy scripts, systemd unit, Secret injection, and fallback, with deploy-script tests.
4. Update the bilingual docs and Agent Note, run the gates, and open the PR.

## Dependencies and boundary

- Dependencies: none; the GitHub Actions runner downloads the Xray binary, no Python dependency is added, and no database or API contract changes.
- Boundary: proxy credentials exist only in the GitHub Secret and the server's `0600` config; the API `.env` carries only the `HE_GIT_PROXY` address, and logs record state and failure class only.
- Non-goals: no global proxy, no proxying of ordinary HTTP egress, no change to the `preview/*` synchronous contract or the 20-second budget, no frontend UI change, no Xray installation in routine deploys, and no cross-border compliance conclusion.

## Verification

```sh
pnpm test:api
pnpm typecheck:api
pnpm lint:api
pnpm verify:flow
pnpm lint:docs
bash -n deploy/bootstrap-server.sh deploy/release.sh deploy/fetch-xray.sh
```

- Proxy-controller unit tests cover disabled mode, the breaker threshold, half-open after cooldown, probe recovery, direct retry after a proxy-layer failure, and success counting.
- Runner unit tests assert that proxy use sets the proxy variables and SSH rewrite, that direct mode removes every proxy variable, and that non-proxy-layer failures do not trip the breaker.
- Config tests cover a valid local address, an invalid scheme, a credential-bearing address, and the direct behavior when production leaves it empty.
- Deploy-script tests cover `inject-config.py --unset`, Xray config extraction/validation, and the invalid-config fallback; shell scripts pass `bash -n`.

## Acceptance

- Without `XRAY_CONFIG`: no proxy config is written, `HE_GIT_PROXY` is not injected, git uses direct access, and current behavior is unchanged.
- With valid configuration: the proxy unit stays resident on loopback, content reads, `ls-remote`, and workspace clone/push use the proxy, and other egress is unaffected.
- With invalid configuration, a proxy that fails to start, or a failed probe: deploy warns and removes `HE_GIT_PROXY`, and the release continues with direct access.
- When the proxy fails at runtime: the API does not restart, requests follow the breaker to direct access, background probes return to the proxy after recovery, and logs carry no credentials.
- The bilingual docs cover first enablement, Secret rotation, and rollback; flow, docs, and focused-test gates pass.

## Gates and CI

- `pnpm test:api`, `pnpm typecheck:api`, `pnpm lint:api`, `pnpm verify:flow`, `pnpm lint:docs`, `pnpm contract:check`.
- `verify:flow --diff` validates the PR title and commit `(#N)` references plus scope coverage.
- New tests cover the proxy state machine, runner environment, configuration validation, and the deploy-script fallback.

## Non-goals

- No global `HTTP_PROXY`/`HTTPS_PROXY` switch.
- No proxying of ordinary API HTTP calls or evaluation-platform requests.
- No change to the synchronous `preview/*` contract, the content-read budget, or asynchrony.
- No Xray node purchase, cross-border compliance conclusion, or frontend UI change.
