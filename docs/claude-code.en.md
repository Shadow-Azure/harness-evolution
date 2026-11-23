# Claude Code

English | [中文](claude-code.md)

Before switching `current`, the production deploy pipeline installs Claude Code for the `deploy` user and writes model configuration from GitHub Secrets. The runner downloads the official apt package, verifies its SHA256, and uploads it; the server only extracts it, with no `claude.ai` access, no root, and no Node.js.

## GitHub Secrets

| Secret | Required | Content |
|---|---|---|
| `CLAUDE_CODE_MODEL` | yes | Model ID, e.g. `MiniMax-M3.1-Flash[1m]` |
| `CLAUDE_CODE_API_KEY` | yes | Model API key |
| `CLAUDE_CODE_BASE_URL` | no (required for MiniMax) | Anthropic-compatible endpoint, must be `https://` (loopback may use `http://`); MiniMax China uses `https://api.minimax.cn/anthropic` |

`CLAUDE_CODE_VERSION` is a Variable, not a Secret; empty selects the latest stable.

## Configuration

The package is extracted to `/opt/harness/shared/claude-code/<version>` (directory 0755), and a stable `current` symlink is created atomically beside it; `~/.local/bin/claude` remains only the `deploy` user's manual entry point. The service uses `current/usr/bin/claude`, upgrades only switch the symlink, and the current and previous versions are kept. Rerunning the same version (including `need_install=false`) repairs the version directory, `usr`, and `usr/bin` permissions.

Service settings live in `/opt/harness/shared/claude-code/config/settings.json` (0644) with `model`, an optional `ANTHROPIC_BASE_URL`, model aliases, and MiniMax's documented 512K auto-compact window (`524288`) and `effort=max`; the file contains no `apiKeyHelper` and no credentials, so `harness` can read it. The `deploy` user's own `~/.claude/settings.json` (0600) and `~/.claude/api-key` (0600) remain for manual CLI use only.

Deploy injects these keys into the 0600 `/opt/harness/shared/.env`: `HE_AI_AGENT_CLAUDE_BIN=/opt/harness/shared/claude-code/current/usr/bin/claude`, `HE_AI_AGENT_CLAUDE_SETTINGS=/opt/harness/shared/claude-code/config/settings.json`, `CLAUDE_CONFIG_DIR=/opt/harness/shared/claude-code/config`, and `ANTHROPIC_API_KEY` (reusing `CLAUDE_CODE_API_KEY`, transported only as base64/stdin). The service passes the environment through to the CLI without reading, persisting, or logging the value.

Before switching `current`, the installer verifies that the binary is other-executable, the settings are other-readable, and every level from `prefix` to the binary (the version directory, `usr`, `usr/bin`) is other-traversable; any failure aborts the release and the old release keeps serving. Deploy rechecks those bits with `stat` (`test -x` always passes from deploy's viewpoint) and, when it has the privilege, smoke-tests `sudo -u harness ... --version`. If all three secrets are absent the step warns and skips; a partial configuration fails.

## Verification

```sh
ver=$(ssh deploy@<host> 'readlink -f /opt/harness/shared/claude-code/current')
ssh deploy@<host> "stat -c '%a %U:%G %n' '$ver' '$ver/usr' '$ver/usr/bin' /opt/harness/shared/claude-code/config/settings.json"
ssh deploy@<host> 'sudo -u harness /opt/harness/shared/claude-code/current/usr/bin/claude --version'
```

The version directory, `usr`, and `usr/bin` must be `755`; the last command is the harness-viewpoint acceptance.

`claude -p` needs the real API key and is a manual acceptance; the pipeline checks installation, shared permissions, and configuration structure only. Production acceptance reads `ai_agent_call.outcome=ok`, tokens > 0, a non-`unknown` model, and no `clusters_created.payload.degraded`.

## Rollback

Point `/opt/harness/shared/claude-code/current` back at the previous version directory, or rerun `Deploy` with the desired `CLAUDE_CODE_VERSION`. Shared settings and `.env` are written atomically, so a failure keeps the previous copy; `current` is decoupled from `HE_AI_AGENT_CLAUDE_BIN`, so a rollback needs no `.env` change. See [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md) for the steps.

For Skill attribution, set `HE_ATTRIBUTION_AGENT=claude` after the service account passes its bubblewrap check. [Deployment](../plans/deploy-aliyun-playbook.md)
