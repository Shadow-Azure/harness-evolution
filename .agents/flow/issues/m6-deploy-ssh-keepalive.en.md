# SSH keepalive for the Deploy workflow

English | [中文](m6-deploy-ssh-keepalive.md)

```yaml flow
kind: issue
id: m6-23
milestone: m6
depends:
  - m6-22
priority: P1
status: ready
scope:
  - .github/workflows/**
  - .agents/flow/**
adr: []
github:
  number: 202
  url: https://github.com/Shadow-Azure/harness-evolution/issues/202
```

## Background

During m6-22's first real release, the SSH session was reset by a network middlebox mid remote pip install (`Connection reset by peer`, exit 255), failing the Deploy run. The server now uses the Aliyun pip mirror to shorten the saturation window, but any long remote step (migrations, large uploads) still rides a default keepalive-less SSH connection — a single network hiccup invalidates the whole release.

## Goals

- Both SSH uses in the Deploy workflow (rsync upload and the remote release script) carry `ServerAliveInterval=30` / `ServerAliveCountMax=6`, actively keeping idle sessions alive so connection jitter self-heals.

## Design authority

- [plans/fullstack-design/01-architecture.md §6 Deployment shape and scaling path](../../../plans/fullstack-design/01-architecture.md): delivery-channel reliability is an operational requirement of that shape; this issue hardens the channel only and changes no deployment semantics.
- m6-22's implementation section (Deploy workflow vs release.sh responsibility split) is the direct predecessor.

## Implementation

- `.github/workflows/deploy.yml`: append the two keepalive parameters to `SSH_CMD` and the release step's ssh command.

## Implementation steps

1. Change `deploy.yml` in the defect-fix PR and advance this issue to ready within the same PR.
2. Validate the real release chain via the Deploy run after merge.

## Dependencies and boundary

- Depends on: m6-22 (the Deploy workflow itself).
- Delivery boundary: only the workflow's ssh parameters; no changes to the release script or server configuration.
- Non-goals: see the dedicated section below.

## Verification

```sh
pnpm verify:flow
```

- `verify:flow` passes fully; the post-merge Deploy run goes green and the server `/api/health` returns 200.

## Acceptance

- The Deploy workflow's ssh commands include the keepalive parameters.
- The post-merge automatic release goes green with a passing health check.

## Gates and CI

- `verify-flow --diff`: titles carry `(#202)`, and the diff lands inside the registered scope.
- This issue is activated from backlog within the defect-fix PR (a legal path per the flow README).

## Non-goals

- No changes to rsync excludes, trigger conditions, or the release script.
- No third-party Actions.
