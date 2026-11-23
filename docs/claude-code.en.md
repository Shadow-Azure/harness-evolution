# Claude Code

English | [中文](claude-code.md)

Deploy installs Claude Code and writes model configuration from GitHub Secrets. The runner downloads, verifies, and uploads the official apt package; the server only extracts it, with no `claude.ai` access and no root or Node.js.

## GitHub Secrets

| Secret | Required | Content |
|---|---|---|
| `CLAUDE_CODE_MODEL` | yes | Model ID, e.g. `MiniMax-M3.1-Flash[1m]` |
| `CLAUDE_CODE_API_KEY` | yes | Model API key |
| `CLAUDE_CODE_BASE_URL` | no (required for MiniMax) | Anthropic-compatible endpoint, `https://` (loopback may use `http://`); MiniMax China uses `https://api.minimax.cn/anthropic` |

`CLAUDE_CODE_VERSION` is a Variable, not a Secret; empty selects the latest stable.

## Configuration

The package is extracted to `/opt/harness/shared/claude-code/<version>` (directory 0755), and a stable `current` symlink is created atomically beside it; the service uses `current/usr/bin/claude`, upgrades only switch the symlink, and the previous version is kept. Rerunning the same version repairs the version directory, `usr`, and `usr/bin` permissions.

Service settings live in `/opt/harness/shared/claude-code/config/settings.json` (0644) with `model`, an optional `ANTHROPIC_BASE_URL`, model aliases, and MiniMax 512K/heavy settings, without credentials. Deploy injects `HE_AI_AGENT_CLAUDE_BIN`, `HE_AI_AGENT_CLAUDE_SETTINGS`, `CLAUDE_CONFIG_DIR`, and `ANTHROPIC_API_KEY` (reusing the Secret) into the 0600 `.env`; the service only passes the environment through.

Before switching `current`, the installer checks that the binary is other-executable, the settings other-readable, and every path level other-traversable; failure aborts and keeps the old release. Deploy rechecks with `stat` and runs `sudo -u harness ... --version` when permitted. If all Secrets are absent the step warns and skips; a partial configuration fails.

## analyze tool surface and permissions

Analyze does not use `--bare`; it always passes `--safe-mode`, `--restricted`, `--strict-mcp-config`, and `--tools Read,Write`, letting the model only read `schema.json` and write `result.json5`.

Permission rules use absolute task-directory paths: `Read(//<task>/schema.json)` and `Edit(//<task>/result.json5)`. File writes are governed only by `Edit(path)` rules; `Bash`, the `Edit` tool, and writes outside the task directory remain denied by `dontAsk`. `--output-format stream-json --verbose` reads the tool list and `permission_denials`/`stop_reason`/`num_turns`; a missing tool or denied write fails immediately.

Acceptance:

```sh
HE_AI_AGENT_CLAUDE_E2E=1 \
HE_AI_AGENT_CLAUDE_BIN=/opt/harness/shared/claude-code/current/usr/bin/claude \
  pnpm test:api -- tests/test_ai_agent_claude_code.py -k e2e_real_cli
```

## Verification

```sh
ver=$(ssh deploy@<host> 'readlink -f /opt/harness/shared/claude-code/current')
ssh deploy@<host> "stat -c '%a %U:%G %n' '$ver' '$ver/usr' '$ver/usr/bin' /opt/harness/shared/claude-code/config/settings.json"
ssh deploy@<host> 'sudo -u harness /opt/harness/shared/claude-code/current/usr/bin/claude --version'
```

The version directory, `usr`, and `usr/bin` must be `755`; the last command is the harness-viewpoint acceptance.

`claude -p` needs the real API key and is a manual acceptance; the pipeline checks installation and configuration structure only. Production acceptance reads `ai_agent_call.outcome=ok`, tokens > 0, a non-`unknown` model, and no `clusters_created.payload.degraded`.

## Rollback

Point `current` back at the previous version directory, or rerun `Deploy` with the desired `CLAUDE_CODE_VERSION`. Shared settings and `.env` are written atomically; `current` is decoupled from `HE_AI_AGENT_CLAUDE_BIN`, so a rollback does not change `.env`. See [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md) for the steps.
