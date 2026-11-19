This is by an automated agent, not a human.

# Install and configure Claude Code in the production deployment pipeline (model via GitHub Secrets)

English | [中文](m15-01-claude-code-deploy.md)

```yaml flow
kind: issue
id: m15-01
milestone: m15
depends:
  - m6-22
priority: P1
status: in-progress
scope:
  - .github/workflows/**
  - deploy/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - scripts/doc-budgets.manifest.json
  - apps/api/tests/**
adr: []
github:
  number: 376
  url: https://github.com/Shadow-Azure/harness-evolution/issues/376
```

## Background

Production `Deploy` runs over SSH as the `deploy` user. Its passwordless sudo is limited to `systemctl restart/start harness-api`, and the server has no Node.js. `claude.ai/install.sh` is region-blocked on the current network, while the official apt repository is reachable. The official `claude-code` deb contains only `./usr/bin/claude`, has no postinst, and depends only on `libc6`, so it can be extracted into a user directory and run directly. The user chose the MiniMax China Anthropic-compatible endpoint, with the model and API key in GitHub Secrets. `harness-api` does not call Claude Code today; this issue only delivers a usable installation and model configuration on the production server.

## Goals

- `Deploy` installs or updates Claude Code before switching `current` and writes the `deploy` user's model configuration; a failure must not break the current release.
- The package is fetched and verified on the runner; the server only extracts it. No server access to `claude.ai`, no root, and no Node.js.
- The model, endpoint, and key come only from GitHub Secrets; the key never enters `settings.json`, logs, the repository, or SSH command lines.
- When all secrets are absent the step is skipped without changing existing deploys; a partial configuration fails explicitly.
- Documents, the deployment playbook, and an Agent Note record the operation, verification, and rollback.

## Design authority

- [plans/fullstack-design/01-architecture.md §6 deployment shape](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/01-architecture.md): single-instance SaaS, nginx + uvicorn, and the boundary between GitHub Secrets and server-local configuration.
- [docs/deployment.md](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/deployment.md): the existing release, secrets, health-check, and rollback conventions.
- [MiniMax Claude Code documentation](https://platform.minimaxi.com/docs/m-plan/claude-code): the China endpoint, the M3.1-Flash model, and the default Sonnet/Opus/Haiku aliases.

## Implementation

- `deploy/fetch-claude-code-deb.sh` (runner side): read the server's `dpkg --print-architecture`, resolve the official apt `Packages` index, download the matching version, verify SHA256, and cache it; `--resolve-only` returns just the version.
- `deploy/install-claude-code.py` (server side): read base64 variables from stdin; extract the deb to `/opt/harness/shared/claude-code/<version>`, self-check it, then atomically switch `~/.local/bin/claude`; atomically write `~/.claude/settings.json`, `~/.claude/api-key`, and `~/.claude/api-key.sh`; validate JSON, permissions, and `claude --version`.
- `.github/workflows/deploy.yml`: add prepare and install steps after "上传 release 与配置" and before release; cache the deb, probe the server version, transfer only when the version changes; skip when all secrets are absent and fail on a partial configuration.
- `docs/deployment.*` and `plans/deploy-aliyun-playbook.md`: document the secret list and the install, configure, verify, and rollback steps; add an Agent Note for the "runner download + user-level extraction + apiKeyHelper" trade-off.
- `apps/api/tests/deploy/test_install_claude_code.py`: cover decoding, version normalization, settings construction, permissions, and base URL validation.

## Implementation steps

1. Create the m15/m15-01 flow files and the branch; confirm m6-22 is done.
2. Implement the runner and server scripts and add unit tests.
3. Wire `deploy.yml` while preserving the existing behavior when secrets are absent.
4. Update the Chinese/English deployment docs, the playbook, and the Agent Note.
5. Run the static gates and focused tests, open a PR, and fix CI and review findings.

## Dependencies and boundary

- Dependency: m6-22 (the existing GitHub Actions release channel).
- Boundary: only the deploy pipeline, `deploy/` scripts, deployment docs/playbook, Agent Note, flow files, and their tests; no change to `apps/` business code, contracts, the database, or the frontend.
- The real `claude -p` smoke test needs the user to replace the placeholder `CLAUDE_CODE_API_KEY` with the real MiniMax key. The pipeline validates installation and configuration structure only; external model availability is not a hard release gate.
- This issue does not integrate Claude Code into `harness-api`; a follow-up issue would handle the runtime user and configuration-directory permissions.

## Verification

```sh
bash -n deploy/fetch-claude-code-deb.sh
python3 -m py_compile deploy/install-claude-code.py
pnpm test:api -- tests/deploy
pnpm verify:flow
pnpm verify:docs
pnpm test:gates
```

- Unit tests cover base64 decoding, version comparison, settings construction, and permissions; `--resolve-only` returns the current stable version from the official apt repository.
- All secrets absent: the install step warns and skips; the rest of `Deploy` matches today.
- All secrets present: `~/.local/bin/claude --version` succeeds on the server; `claude doctor` reports no settings error; `claude -p "只回复 OK"` returns a model response (manual, with the real key).
- Rerunning the same version does not download or extract again; a version change only switches the symlink; failures happen before the `current` switch.

## Acceptance

- With the three secrets configured, one normal `Deploy` yields an executable Claude Code and the MiniMax model configuration.
- `~/.claude/settings.json` and `~/.claude/api-key` are mode 600, and the key is absent from settings, logs, and the repository.
- All secrets absent leaves the deploy unchanged; a partial configuration fails explicitly; an install failure does not switch `current`.
- The server needs neither root nor Node.js; `harness-api` and the existing release flow are unaffected.
- Docs and the playbook include the secret list, verification commands, and rollback steps.

## Gates and CI

- `docs-flow` (`verify:flow --diff`): PR title and commits contain `(#376)`, and changes fall inside this issue's scope.
- The existing `static`, `test`, `docs`, and `flow-online` lanes; `pnpm verify:docs`, `pnpm test:gates`, `bash -n`, and `py_compile`.
- `deploy.yml` does not run in the PR lane; the real deploy happens after merge, triggered by a person or by main CI, and `claude -p` is accepted manually.

## Non-goals

- No Claude Code integration into `harness-api`, and no change to `apps/`, `packages/contracts`, the database, or the frontend.
- No system-level `/usr/bin` install, no widening of the `deploy` user's sudo permissions, and no Node.js.
- No Claude Code auto-updates, no multi-user shared configuration, and no multi-model routing or automatic fallback.
- No production key in `.env`, the repository, an image, or logs; no real key in an issue or PR.
- No hard release gate on external model availability; a manual smoke test covers the real call.
