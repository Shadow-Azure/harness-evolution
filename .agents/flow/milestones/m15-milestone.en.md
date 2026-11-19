# M15 Production Claude Code operations

English | [中文](m15-milestone.md)

```yaml flow
kind: milestone
id: m15
title: M15 生产环境 Claude Code 运维
status: done
github:
  number: 23
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/23
```

## Goals

Make the production deploy pipeline install and configure Claude Code before release: the package is fetched and verified on the GitHub Actions runner, the server extracts it as the deploy user under `/opt/harness/shared/claude-code`, and the model, endpoint, and key are written to `~/.claude` from GitHub Secrets. No server access to `claude.ai`, no root, and no Node.js.

## Scope

The install and configure scripts under `deploy/`, the install step in `.github/workflows/deploy.yml`, `docs/deployment.*` and the deployment playbook, the matching Agent Note, and the flow files. The first supported model provider is the MiniMax China Anthropic-compatible endpoint.

## Acceptance

With the three Claude Code secrets configured, one normal `Deploy` yields an executable `~/.local/bin/claude` on the server and `claude -p` returns a model response. Secrets never appear in the repository, logs, `settings.json`, or SSH command lines. A deploy with all secrets absent behaves exactly as today. Install failures happen before the `current` switch, and reruns are idempotent.

## Non-goals

No Claude Code integration into `harness-api`, no system-level `/usr/bin` install, no widening of the deploy user's sudo permissions, no Node.js, no auto-updates, and no multi-user shared configuration.

## Known follow-up

The real `claude -p` smoke test needs the user to replace the placeholder API key with the real MiniMax key. The pipeline validates installation and configuration structure only; external model availability is not a hard release gate.
