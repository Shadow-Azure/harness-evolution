# Make the Claude Code version directory executable by the service account

English | [中文](bugfix-claude-code-shared-permissions.md)

```yaml flow
kind: issue
id: bugfix-28
milestone: bugfix
depends:
  - bugfix-26
priority: P2
status: in-progress
scope:
  - .agents/**
  - plans/**
  - deploy/**
  - .github/workflows/**
  - apps/api/tests/**
  - docs/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-23-claude-code-shared-directory-permissions.md
github:
  number: 531
  url: https://github.com/Shadow-Azure/harness-evolution/issues/531
```

## Background

On 2026-11-23 at 14:22, production run `01M83H4MV03G85R4SD5K91CK80` failed at the cluster stage: `cluster cluster.review failed: AgentProviderError: claude-code analysis call could not start`. The `ai_agent_call` shows `cluster.review` failing within 10 ms with 0 tokens and `model=unknown`, followed by `run_failed` with `stage=cluster`. The process fails during spawn, not because of the model, network, or credentials.

The same failure predates the #526 deployment: the 10:40 run `01M834EBAY3C9BB3TM8V85VHQN` and the 14:06 run `01M83G629FXGVG2V64AYXYAHP0` each had three `outcome=error` calls for `cluster.review` / `cluster.score` / `severity.score` (7–10 ms, 0 tokens), but they were silently degraded to fallback confidence/severity, the run still completed, and the final score was 85. #526 made real-provider failures strict and moved the CLI/settings to service-level shared paths, so the failure surfaced explicitly for the first time. #526 made the problem visible; it did not create it.

Direct cause: `install_from_deb()` in `deploy/install-claude-code.py` extracts the deb into a `tempfile.mkdtemp()` directory (0700 by default) and renames it to `/opt/harness/shared/claude-code/<version>` with `os.replace(staging, target)`. The version directory keeps 0700 and the `deploy` owner. The service runs as `harness` (`User=harness`, no home, no ACL, a different group from deploy), cannot traverse that directory, and cannot execute `current/usr/bin/claude`; `execve` returns EACCES, Python normalizes it to `OSError`, and it becomes `AgentProviderError: claude-code analysis call could not start`.

Why the deployment stayed green: the `preflight_shared_access()` added by #526 checks `prefix`, `config`, the settings file, and the binary's other-execute bit, but not `<version>` / `usr` / `usr/bin`. The `deploy.yml` preflight uses `test -x "$BIN"` over SSH as deploy; deploy owns the directory and always passes. The installer's own `--version` is also a deploy-viewpoint check. The process that actually executes the CLI is harness, and no check used the service account's viewpoint.

Conclusion: the root cause is the installer permission handling introduced by #379 (a 0700 version directory). #526 fixed the right problem, but its new preflight missed the version directory and did not repair existing 0700 directories, so "a new path still cannot start". Fixing the preflight alone is not enough: the current deployment takes the configure-only path with `need_install=false`, never calls `install_from_deb()`, and existing directories must be repaired separately.

### Root-cause investigation

1. Read the production run `01M83H4MV03G85R4SD5K91CK80` events: seq 6 is the `ai_agent_call` for `cluster.review` with `outcome=error`, `latencyMs=10`, `totalTokens=0`, and `model=unknown`; seq 7 is `run_failed` with `stage=cluster` and a `ClusterAIFailure` wrapping `AgentProviderError: claude-code analysis call could not start`. `/steps/clusters` returns `failurePolicy=strict`, `clusters=[]`, and the same failure text.
2. Compare the pre-#526 runs: `01M834EBAY3C9BB3TM8V85VHQN` (10:40) and `01M83G629FXGVG2V64AYXYAHP0` (14:06) each had three `error` calls with `degraded.reason` equal to `AgentProviderError: claude-code analysis call could not start`, but both runs completed. That proves the CLI could not start before #526 and was hidden by silent degradation.
3. Read Deploy run `45121827113` (sha `8e907591`): the installer printed `shared-settings: /opt/harness/shared/claude-code/config/settings.json` and `stable-binary: /opt/harness/shared/claude-code/current/usr/bin/claude`; the preflight printed "shared asset preflight passed"; 11 configuration entries were injected, including `HE_AI_AGENT_CLAUDE_BIN`, `HE_AI_AGENT_CLAUDE_SETTINGS`, `CLAUDE_CONFIG_DIR`, and `ANTHROPIC_API_KEY`; `harness-api` restarted and passed its health check at 14:07:15. The env, symlink, and pipeline all succeeded; only the service account's execution viewpoint failed.
4. Read the installer: `install_from_deb()` creates a 0700 staging directory and `os.replace()` preserves that mode; `binary.exists()` returns early and does not repair an existing directory; `preflight_shared_access()` checks only `prefix` and `settings.parent`, not the version directory, `usr`, or `usr/bin`.
5. Check the deployed `claude-code_2.1.323-1` deb: `data.tar.gz` has no `./` root entry, its first entry is `./usr`, and extraction cannot restore the staging directory to 0755 through a root entry; `usr/bin/claude` is 0755. Combined with `mkdtemp()`'s 0700, the version directory stays 0700.
6. Conclusion: harness cannot execute the CLI on the shared path. The fix must cover both "new extraction" and "existing directory", and the preflight must check the whole directory chain.

### User requirements

- Fix the root cause directly; do not only add a Secret, update docs, or add a warning.
- Prefer a pure-pipeline fix: if rerunning Deploy is enough, do not require manual server work; if root or manual steps are unavoidable, state the minimal steps, why they are needed, and how to roll back.
- No faking: a real provider failure must fail explicitly, never fall back to a confidence/severity value or show "self-evolution effective".
- Verifiable: after deployment a real run's `cluster.review` must be `outcome=ok`, tokens > 0, and model not `unknown`, with no `could not start`.
- Keep the security boundary: keep the two deploy/harness users and least privilege; do not accept 0777, running the service as deploy, or committing secrets.

## Goals

- Let harness execute `/opt/harness/shared/claude-code/current/usr/bin/claude`; the version directory and its ancestors must be traversable by the service account.
- Deploy must detect "the service account cannot execute" before switching `current` and abort, rather than deploying green and failing at runtime.
- The fix must cover repeat deployments with `need_install=false`: a historical 0700 directory is repaired by rerunning Deploy, without root or manual chmod.
- A real run's `cluster.review` becomes `outcome=ok`, tokens > 0, model not `unknown`, with no `degraded`.

## Design authority

- [07 §5.5.1 AI Agent provider outbound adapter](../../../plans/fullstack-design/07-backend-implementation.md): provider contract, the `cluster.review` / `cluster.score` / `severity.score` task keys, and failure normalization.
- [07 §5.5.2 Three-layer clustering: grouping / review / scoring](../../../plans/fullstack-design/07-backend-implementation.md): strict failure semantics for review / score / severity in real mode.
- [docs/claude-code.md](../../../docs/claude-code.en.md): current installation, shared settings, preflight, and verification commands for the service-level CLI assets.
- [bugfix-ai-agent-real-mode-no-degrade](bugfix-ai-agent-real-mode-no-degrade.en.md): the upstream decision for strict failure and the shared `current` path; this issue closes its deployment permission gap.

## Implementation

- `deploy/install-claude-code.py`: set the version directory (including `usr` and `usr/bin`) to 0755 after extraction; also repair an existing version directory on the `binary.exists()` early-return branch.
- `deploy/install-claude-code.py`: on the configure-only path (`need_install=false`, no `--deb`), locate the version directory behind `current` and repair its permissions, so rerunning Deploy repairs a historical 0700 directory.
- `deploy/install-claude-code.py`: make `preflight_shared_access()` check other-execute on every level from `prefix` to the binary (at least `<version>`, `usr`, `usr/bin`), keep the settings other-read check, and fail before `switch_current`.
- `.github/workflows/deploy.yml`: stop relying only on `test -x` (deploy's viewpoint); check the other bits at every level with `stat`, and when deploy has the privilege, add a `sudo -u harness .../current/usr/bin/claude --version` smoke test.
- `apps/api/tests/deploy/test_install_claude_code.py`: add the "a 0700 version directory must fail the preflight" case and the "`install_from_deb()` leaves the version directory 0755" assertion; fix the existing fixture that chmods 0755 before the preflight and hides the real defect.
- `docs/claude-code.md` / `docs/claude-code.en.md`: update the preflight and acceptance instructions with the version-directory permissions and the harness-viewpoint verification command.
- `.agents/notes/`: record the decision that the preflight must cover the whole path and the installer must repair existing version directories.

## Implementation steps

1. Change `install_from_deb()` and the existing-directory path to repair the version directory and its ancestors consistently.
2. Extend `preflight_shared_access()` and update the `deploy.yml` preflight.
3. Add installer and preflight tests covering a real 0700 directory and the 0755 result after installation.
4. Update `docs/claude-code.md` / `.en.md` and the Agent Note.
5. Rerun Deploy and confirm harness can execute the CLI and a real run succeeds, per "Verification".
6. If verification still fails, check whether the running process receives `HE_AI_AGENT_CLAUDE_BIN` (systemd `EnvironmentFile` and restart ordering), but do not change the CLI path again.

## Dependencies and boundary

- Depends on: bugfix-26 (#521 / #526 are merged).
- Non-goals: do not change the provider contract, clustering algorithm, or strict/degrade semantics; do not add a Secret; do not run the service as deploy; do not use 0777; do not commit secrets; do not change patch/edit semantics; do not rewrite the version-retention policy.

## Verification

```sh
# 1) After deployment, verify from the service account's viewpoint
ssh deploy@<host> '
  ver=$(readlink -f /opt/harness/shared/claude-code/current)
  stat -c "%a %U:%G %n" "$ver" "$ver/usr" "$ver/usr/bin" "$ver/usr/bin/claude"
  sudo -u harness "$ver/usr/bin/claude" --version
'
# Expected: the version directory is 755; harness prints 2.1.323 (Claude Code)

# 2) Real-run acceptance
# Start a cluster-only preview or self-evolution run and check the events:
# ai_agent_call: task=cluster.review, outcome=ok, totalTokens>0, model != unknown
# No degraded and no AgentProviderError ... could not start
```

- `pnpm test:api -- tests/deploy/test_install_claude_code.py`
- `pnpm test:gates`
- `pnpm verify:flow`
- `pnpm verify:docs`

## Acceptance

- After deployment, `sudo -u harness /opt/harness/shared/claude-code/current/usr/bin/claude --version` succeeds; the version directory, `usr`, and `usr/bin` are 0755.
- A 0700 version directory fails the preflight before `current` switches; "green deploy but unusable service" no longer happens.
- A repeat deployment with `need_install=false` repairs the historical 0700 directory.
- A real run's `cluster.review` is `outcome=ok`, tokens > 0, and model not `unknown`; there is no `degraded`.
- Unit tests cover the 0700 preflight failure and the 0755 result after installation; `docs/claude-code.md` / `.en.md` are in sync.

## Gates and CI

- `pnpm test:api -- tests/deploy/test_install_claude_code.py`
- `pnpm test:gates`
- `pnpm verify:flow`
- `pnpm verify:docs`
- Commit and PR titles contain `(#531)`; review follows `docs/review.md`, and the review document goes under `plans/`.

## Non-goals

- Do not change how `AgentProviderError.detail` is exposed, the `/api/health` AI Agent fields, or the startup health UI (a separate observability issue can do that).
- Do not change the model, gateway, base URL, or credential configuration.
- Do not introduce root/ACL/`LoadCredential`; prefer a pure-pipeline fix.
- Do not rewrite the installer's version-retention policy or the deploy/harness user model.
