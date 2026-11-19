# M18 Production git egress proxy and fallback

English | [中文](m18-milestone.md)

```yaml flow
kind: milestone
id: m18
title: M18 生产 Git 出网代理与失效回退
status: planned
github:
  number: 27
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/27
```

## Goals

When production access to GitHub is unstable, let the server read target repositories, list versions, and sync workspaces through a local Xray/VLESS proxy that serves git subprocesses only. The proxy config arrives through a GitHub Secret; healthy requests use the proxy, failures fall back to a direct connection inside the running process, and missing or invalid configuration returns fully to direct access without affecting other API egress.

## Scope

Xray installation, config rendering, systemd unit, and bootstrap under `deploy/`, the Secret wiring and pre-deploy probe in `.github/workflows/deploy.yml`, the proxy-aware runner and health state machine under `apps/api/app/third_party_api/git/`, configuration and assembly in `apps/api/app/config.py` and `main.py`, the proxy operations docs under `docs/`, plus the matching flow files and Agent Note.

## Acceptance

- Without `XRAY_CONFIG`: nothing is installed or started, the API injects no `HE_GIT_PROXY`, and git uses direct access with unchanged behavior.
- With valid configuration: the proxy unit stays resident on a loopback mixed inbound, and the API's git subprocesses (content reads, `ls-remote`, workspace clone/push) use the proxy through `HE_GIT_PROXY` while other egress is unaffected.
- With invalid configuration, a proxy that fails to start, or a failed tunnel probe: the deploy warns and removes `HE_GIT_PROXY`, and the release continues with direct access.
- When the proxy fails at runtime: consecutive failures open the circuit to direct access, a single proxy-layer failure retries that request directly, and background probes return to the proxy after recovery without restarting the API.
- Logs record state, failure class, and timing only; never UUIDs, public keys, server addresses, or the full config.
- The bilingual operations docs cover the Secret shape, key fields, first enablement, rotation, and rollback; flow and docs gates pass.

## Non-goals

No global `HTTP_PROXY`/`HTTPS_PROXY` switch, no proxying of ordinary API HTTP calls, no change to the `preview/*` synchronous contract or the 20-second content budget, no Xray installation in routine deploys, no cross-border compliance conclusion, and no frontend UI change.
