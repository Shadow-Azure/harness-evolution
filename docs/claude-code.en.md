# Claude Code

English | [中文](claude-code.md)

Before switching `current`, the production deploy pipeline installs Claude Code for the `deploy` user and writes model configuration from GitHub Secrets. The runner downloads the official apt package, verifies its SHA256, and uploads it; the server only extracts it, with no `claude.ai` access, no root, and no Node.js.

## GitHub Secrets

| Secret | Required | Content |
|---|---|---|
| `CLAUDE_CODE_MODEL` | yes | Model ID, e.g. `MiniMax-M3.1-Flash[1m]` |
| `CLAUDE_CODE_API_KEY` | yes | Model API key |
| `CLAUDE_CODE_BASE_URL` | no | Anthropic-compatible endpoint; MiniMax China uses `https://api.minimax.cn/anthropic` |

`CLAUDE_CODE_VERSION` is a Variable, not a Secret; empty selects the latest stable.

## Configuration

The package is extracted to `/opt/harness/shared/claude-code/<version>`, and `~/.local/bin/claude` atomically points at the current version; the current and previous versions are kept. `~/.claude/settings.json` (0600) holds `model`, an optional `ANTHROPIC_BASE_URL`, and `apiKeyHelper`; the real key lives in `~/.claude/api-key` (0600), read by the 0700 helper, and never enters settings. MiniMax receives the documented 1M auto-compact window, `effort=max`, and Sonnet/Opus/Haiku aliases pinned to the model.

If all three secrets are absent the step warns and skips; a partial configuration fails; install/configure failures abort before the `current` switch and the old release keeps serving. Rerunning the same version only rewrites configuration; it does not download or extract again.

## Verification

```sh
ssh deploy@<host> '~/.local/bin/claude --version'
ssh deploy@<host> '~/.local/bin/claude doctor'
ssh deploy@<host> '~/.local/bin/claude -p "只回复 OK"'
```

`claude -p` needs the real API key and is a manual acceptance; the pipeline checks installation and configuration structure only.

## Rollback

Point `~/.local/bin/claude` back at the previous version directory, or rerun `Deploy` with the desired `CLAUDE_CODE_VERSION`. `~/.claude/settings.json` and `api-key` are written atomically, so a failure keeps the previous copy. See [plans/deploy-aliyun-playbook.md](../plans/deploy-aliyun-playbook.md) for the steps.
