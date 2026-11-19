# Agent Note: Production git egress proxy and fallback

Status: implemented

English | [中文](2026-11-19-git-egress-proxy.md)

## Problem

When production reads a target repository's `SKILL.md` / `AGENT.md`, a cold cache triggers git operations against GitHub; mainland links often cannot finish within 20 seconds, so users see "target file read timed out". Single-ref shallow fetch reduces the payload, but egress itself remains unstable, so an optional proxy is needed.

The proxy cannot be implemented by putting a VLESS string into `HTTPS_PROXY`: VLESS is an Xray outbound protocol, while git only understands an HTTP CONNECT or SOCKS proxy; production needs a local client that turns the VLESS outbound into an HTTP inbound on loopback. Nor can it rely on editing `.env` and waiting for a running process to pick it up: systemd `EnvironmentFile` is read only at start, restarting the API interrupts in-flight evolution jobs, and a failing health check can cause a restart storm. A global `HTTP_PROXY` would also bind upstream sync, evaluation, and internal calls to the proxy, and one missing `NO_PROXY` entry can cause an incident.

## Decision

- The configuration entry point is one GitHub Environment Secret, `XRAY_CONFIG` (complete Xray JSON). The pipeline validates the structure on the runner and accepts only a loopback `mixed`/`http` inbound and a `vless` outbound; the server atomically writes `/opt/harness/shared/proxy/config.json` (`0600`, owned by `deploy`), and it never enters the repository, the API `.env`, logs, or the PR.
- The runner downloads the Xray binary from the official release with a pinned `v26.11.9` and amd64/arm64 SHA256, and uploads it with `geoip.dat`/`geosite.dat`; the server does not access GitHub, avoiding the chicken-and-egg of needing a proxy to install the proxy. `harness-proxy.service` runs as `deploy`, listens on loopback only, and is installed idempotently by bootstrap.
- The API adds only one credential-free variable, `HE_GIT_PROXY=http://127.0.0.1:<port>`. `ProxyAwareGitRunner` injects at the three existing runner seams: `SubprocessGitContent`, `SubprocessGitRemote`, and `GitWorkspaceManager`; when proxying it sets `HTTPS_PROXY`/`HTTP_PROXY` and rewrites GitHub SSH to HTTPS for clone/fetch/ls-remote (push keeps the original remote to preserve SSH auth), and when direct it removes every proxy variable. Other HTTP egress is unaffected.
- An in-process state machine decides whether to proxy: `closed` uses the proxy, three consecutive proxy-layer failures open the circuit to direct access, a background HTTPS HEAD probe through the proxy after the cooldown enters `half_open`, and two consecutive successes close it again. A single request that hits a proxy-layer failure retries directly once; a healthy proxy with a slow GitHub stays a content-read timeout and is not mistaken for a proxy failure. State is not persisted, so a deploy or restart starts at `closed`.
- Before writing `.env`, deploy runs one tunnel probe; only a successful probe injects `HE_GIT_PROXY`, otherwise it removes the stale value, stops the proxy, deletes the server config, and the release continues. A missing Secret, invalid JSON, failed download/checksum, missing unit, failed start, or failed probe all follow the same direct fallback.
- Logs record only `git.proxy.state`, failure counts, and failure class; the proxy address is a local loopback address, and UUIDs, public keys, and server addresses exist only in the Secret and the `0600` config file.

## Alternatives considered

- **Global `HTTPS_PROXY` plus a `NO_PROXY` list.** Rejected: the scope is uncontrollable and any omission sends internal calls through the proxy; a proxy failure would affect all egress, while this change only fixes git reads.
- **Edit `.env` and restart the API when the proxy fails at runtime.** Rejected: environment variables do not hot-reload, a restart interrupts evolution jobs, and failed health checks can cause a restart storm; runtime fallback should be an in-process boolean state.
- **Wrap each request in a temporary `curl`/shell proxy.** Rejected: it adds process and timeout layers, scatters error classification, and bypasses the existing runner's cancellation and process-group cleanup.
- **Use SSH `ProxyCommand` for every remote.** Rejected: it needs an extra `connect` tool and non-GitHub SSH still cannot reuse an HTTP proxy; rewriting GitHub SSH to HTTPS is smaller and testable.
- **Install Xray on the production server.** Rejected: the server's link to GitHub is exactly the problem, so the download would fail first; downloading and verifying on the runner before upload is more reliable.
- **Keep the proxy config in `.env` alongside application config.** Rejected: it would bring UUIDs and public keys into the API process and its backups; separating the Secret and the local config file is smaller.

## Consequences

- First enablement needs one root action: rerun `deploy/bootstrap-server.sh` as root to install `harness-proxy.service` and the matching sudo permissions; later Secret rotation only needs a redeploy.
- The proxy is a single point; a dead node, rate limit, or TLS fingerprint change makes the probe fail, and the system falls back to direct access without switching nodes automatically. Monitoring and manual node changes are required.
- Without the Secret, behavior is exactly as before; with it, git subprocesses use the proxy and other egress is unchanged. The `preview/*` contract, the 20-second content budget, and body-hash semantics do not change.
- Deploy adds `fetch-xray.sh`, `xray-config.py`, and `inject-config.py --unset`; config, runner, and state machine have unit tests, and logs and docs carry no proxy credentials.
- Non-GitHub SSH remotes are not rewritten and do not use the HTTP proxy; switch them to HTTPS or configure `ProxyCommand` separately.
