# Git egress proxy

English | [中文](git-proxy.md)

When production access to GitHub is unstable, git subprocesses can use a local Xray/VLESS proxy. The proxy covers target repository reads, `ls-remote`, and evolution workspace clone/push only; other API egress stays direct. Credentials exist only in the GitHub Environment Secret and a server-local file, while the API receives a credential-free local HTTP address.

## Path

```text
git subprocess --HTTPS_PROXY--> 127.0.0.1:10808 (Xray mixed inbound)
                                      |
                                      +--VLESS/REALITY--> proxy host --> github.com
```

VLESS is an Xray outbound protocol, not an HTTP proxy, so it cannot go directly into `HTTPS_PROXY`. The server needs a resident Xray client that turns the VLESS outbound into a mixed/HTTP inbound on loopback; `deploy/harness-proxy.service` runs that client.

## GitHub Secret

| Name | Location | Content |
|---|---|---|
| `XRAY_CONFIG` | Secret in the `production` Environment | Complete Xray JSON |

`XRAY_CONFIG` is the only new Secret. The pipeline sends it to the server over base64 + stdin and writes `/opt/harness/shared/proxy/config.json` (`0600`, owned by `deploy`); it never enters the repository, the API `.env`, logs, issues, or PR descriptions.

The config must satisfy at least:

- One inbound whose `protocol` is `mixed` or `http`; `listen` must be `127.0.0.1`, `localhost`, or `::1`, with a valid port. The pipeline derives `HE_GIT_PROXY=http://127.0.0.1:<port>` from it.
- One outbound whose `protocol` is `vless`, with `settings.address`, `settings.port`, `settings.id`, `encryption: "none"`, `flow: "xtls-rprx-vision"`, plus `streamSettings.security: "reality"` and `realitySettings` entries for `serverName`, `fingerprint`, `publicKey`, and `shortId`.
- The inbound must not listen on `0.0.0.0` or `::`; otherwise config validation fails and falls back to direct access, because a local proxy must never become a public open proxy.
- `dns` and `routing` are optional; when they reference `geosite:` / `geoip:`, keep `geosite.dat` / `geoip.dat` from the release bundle, which the pipeline uploads too.

The placeholder example only shows the shape; you fill the real values in the Secret:

```json
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    {
      "tag": "mixed",
      "listen": "127.0.0.1",
      "port": 10808,
      "protocol": "mixed",
      "settings": { "auth": "noauth", "udp": true }
    }
  ],
  "outbounds": [
    {
      "tag": "proxy",
      "protocol": "vless",
      "settings": {
        "address": "<PROXY_HOST>",
        "port": 443,
        "id": "<VLESS_UUID>",
        "encryption": "none",
        "flow": "xtls-rprx-vision"
      },
      "streamSettings": {
        "network": "raw",
        "security": "reality",
        "realitySettings": {
          "serverName": "<REALITY_SERVER_NAME>",
          "fingerprint": "chrome",
          "publicKey": "<REALITY_PUBLIC_KEY>",
          "shortId": "<REALITY_SHORT_ID>"
        }
      }
    },
    { "tag": "direct", "protocol": "freedom" },
    { "tag": "block", "protocol": "blackhole" }
  ]
}
```

## Deploy pipeline

Before writing `.env`, `Deploy` runs the following steps; any failure only warns and falls back to direct access instead of blocking the release:

1. `deploy/xray-config.py --extract` validates the JSON, loopback inbound, and VLESS outbound on the runner, and derives the local proxy address.
2. `deploy/fetch-xray.sh` downloads the pinned Xray release for the server architecture (`v26.11.9`, with fixed SHA256 values for amd64/arm64) and extracts `xray`, `geoip.dat`, and `geosite.dat`.
3. It uploads them to `/opt/harness/shared/proxy/bin/`, writes the config atomically, and runs `sudo systemctl restart harness-proxy`.
4. It waits for the unit to become active and probes the tunnel once with `curl -x <local proxy> https://api.github.com/zen`.
5. `HE_GIT_PROXY` is written to `.env` only after the probe succeeds; otherwise `inject-config.py --unset HE_GIT_PROXY` removes a stale value and the API goes direct.

A missing Secret, invalid config, failed download/checksum, missing unit, failed start, or failed probe all follow the same direct fallback. When the unit is not installed, the pipeline tells you to rerun `deploy/bootstrap-server.sh` as root.

## Runtime health and fallback

The API keeps an in-process state machine that only decides whether git subprocesses use the proxy:

- `closed`: the proxy is healthy and git subprocesses get `HTTPS_PROXY`/`HTTP_PROXY`; GitHub `git@github.com:` and `ssh://git@github.com/` remotes are rewritten to HTTPS inside the subprocess, while non-GitHub SSH remotes are unaffected.
- Proxy-layer failures (connection refused, proxy handshake failure, 407, CONNECT 502): three consecutive failures move to `open` and subsequent requests go direct; a single request that hits a proxy-layer failure retries directly once.
- `open`: background probes retry after the cooldown; one success enters `half_open`, and two consecutive successes return to `closed`.
- A healthy proxy with a slow GitHub does not switch to direct; it stays a content-read timeout, so a slow link is not mistaken for a proxy failure.
- State is process-local and starts at `closed` after a deploy or restart; fallback happens without restarting the API or editing `.env`. Logs record state, failure counts, and failure class only, never UUIDs or config content.

Tune the probe interval and per-probe bound with `HE_GIT_PROXY_PROBE_INTERVAL_SECONDS` / `HE_GIT_PROXY_PROBE_TIMEOUT_SECONDS`, defaulting to 60 / 5 seconds.

## First enablement and rotation

1. Add the `XRAY_CONFIG` Secret to the GitHub Environment `production` with the real Xray JSON.
2. The first enablement needs a root rerun of `deploy/bootstrap-server.sh` on the server to install `harness-proxy.service` and the matching sudo permissions; this is one-time environment initialization.
3. Trigger `Deploy`; confirm proxy readiness in the log or look for the fallback warning.
4. Rotate credentials by updating the `XRAY_CONFIG` Secret and redeploying; the pipeline replaces the config atomically and restarts the proxy, with no API config change.
5. Roll back by deleting the Secret or deploying an invalid config; the pipeline removes `HE_GIT_PROXY` and stops the proxy. You can also run `sudo systemctl stop harness-proxy` on the server, and the API breaker moves git to direct access.

## Limits and boundaries

- The proxy is a single point: a dead node, rate limit, or TLS fingerprint change all fail; the health probe falls back to direct but does not switch nodes automatically.
- It covers git subprocesses only. Ordinary API HTTP calls, evaluation-platform requests, and upstream sync do not use this proxy.
- Non-GitHub SSH remotes are not rewritten and do not use an HTTP proxy; switch them to HTTPS or configure `ProxyCommand` separately.
- GitHub SSH remotes are rewritten to HTTPS in proxy mode; a private repository that relies on SSH keys needs HTTPS credentials or the proxy disabled.
- The proxy does not change the `preview/*` synchronous contract or the 20-second content-read budget; a cold clone can still time out.
- Cross-border links and self-hosted proxies need organizational compliance and security review first; this page covers operations wiring only.

## Troubleshooting

- Use `systemctl status harness-proxy` and `journalctl -u harness-proxy` for client state; logs must not contain UUIDs or the full config.
- Verify the tunnel manually with `curl -x http://127.0.0.1:<port> --max-time 5 https://api.github.com/zen`.
- In API logs, `git.proxy.state` at `open` means the breaker already uses direct access, and `git.proxy.retry_direct` means one request fell back; check the proxy unit and Secret.
- A missing `HE_GIT_PROXY` in `.env` means the current deploy uses direct access, usually because the Secret is missing or the proxy probe failed.
