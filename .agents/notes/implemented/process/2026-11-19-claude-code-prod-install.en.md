# Agent Note: Production Claude Code installation and model configuration

Status: implemented

English | [中文](2026-11-19-claude-code-prod-install.md)

## Problem

Production `Deploy` runs over SSH as the `deploy` user, whose passwordless sudo is limited to `systemctl restart/start harness-api`, and the server has no Node.js. Claude Code must be available before release with a MiniMax model configured from GitHub Secrets, while `claude.ai/install.sh` is region-blocked on the current network and cannot be relied on from the server.

## Decision

The GitHub Actions runner resolves and downloads the official apt package and verifies the SHA256 from its `Packages` index. The server, as the `deploy` user, extracts the deb to `/opt/harness/shared/claude-code/<version>` and atomically switches `~/.local/bin/claude`. Model configuration lives under `~/.claude`: `settings.json` (0600) holds `model`, an optional `ANTHROPIC_BASE_URL`, and `apiKeyHelper`; the real key lives in `api-key` (0600), read by `api-key.sh` (0700), and never enters settings. The MiniMax China endpoint is `https://api.minimax.cn/anthropic` with model `MiniMax-M3.1-Flash[1m]`; the documented 512K auto-compact window (`524288`), `effort=max`, and Sonnet/Opus/Haiku aliases are written too, and `~/.claude.json` merges `hasCompletedOnboarding: true`. All three secrets absent skips the step; a partial configuration fails; install/configure failures abort before the `current` switch.

## Alternatives considered

Server-side `curl https://claude.ai/install.sh | bash`: region-blocked on the current network and brings install-time network risk into the release. `npm install -g @anthropic-ai/claude-code`: requires an extra Node.js runtime and a larger attack surface. System-wide install from the official apt repository: requires widening the `deploy` user's sudo, against the existing least-privilege boundary. Putting the key in `settings.json`'s `env`: it would be inherited by every Bash subprocess Claude Code starts; `apiKeyHelper` avoids that. Integrating Claude Code into `harness-api`: outside this issue's operations boundary; a separate issue.

## Consequences

The first install or a version change uploads a roughly 128MB deb, and the server keeps the current and previous versions (about 560MB); rerunning the same version only rewrites configuration. A real `claude -p` needs the user to replace the placeholder key with the real MiniMax key; the pipeline validates installation and configuration structure only. MiniMax-specific environment values are selected by provider in `build_settings`, so a provider change needs a branch adjustment. Auto-updates are disabled; the version comes from the `CLAUDE_CODE_VERSION` Variable or the latest stable.
