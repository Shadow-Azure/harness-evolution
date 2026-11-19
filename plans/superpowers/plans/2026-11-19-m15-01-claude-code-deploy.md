# Claude Code production deployment implementation plan

> **For agentic workers:** this plan follows the superpowers task-by-task style; the linked issue `.agents/flow/issues/m15-01-claude-code-deploy.md` is the implementation contract.

**Goal:** Make the production `Deploy` install and configure Claude Code for the `deploy` user from GitHub Secrets, without root, Node.js, or server access to `claude.ai`.

**Architecture:** The GitHub Actions runner resolves the official apt package and verifies its SHA256; the server extracts it into `/opt/harness/shared/claude-code/<version>`, switches `~/.local/bin/claude`, and writes `~/.claude` with an `apiKeyHelper`. The step runs after the release upload and before the `current` switch, so a failure leaves the running release untouched.

**Scope:** `.github/workflows/deploy.yml`, `deploy/`, `docs/`, `plans/`, `.agents/flow/`, `.agents/notes/`, `scripts/doc-budgets.manifest.json`, `apps/api/tests/deploy/`.

### Task 1: Runner package resolution

**Files:** Create `deploy/fetch-claude-code-deb.sh`.

- [x] Resolve the server architecture and the official apt `Packages` index.
- [x] Select the requested version or the highest stable version.
- [x] Download the deb, verify SHA256, and support `--resolve-only` and a cache directory.

### Task 2: Server install and configuration

**Files:** Create `deploy/install-claude-code.py`; create `apps/api/tests/deploy/test_install_claude_code.py`.

- [x] Decode `KEY <base64>` stdin and reject malformed values.
- [x] Extract the deb into a versioned prefix, self-check the binary, and atomically switch the launcher.
- [x] Write `settings.json`, `api-key`, `api-key.sh`, and `~/.claude.json` onboarding with 0600/0700 permissions; keep the key out of settings.
- [x] Apply MiniMax's documented aliases, 512K auto-compact window, and effort level.
- [x] Unit-test the pure functions and the permission layout.

### Task 3: Workflow integration

**Files:** Modify `.github/workflows/deploy.yml`.

- [x] Probe the installed version, then cache/download only the exact target version.
- [x] Skip when all three secrets are absent; fail on a partial configuration.
- [x] Run the install/configure step after the release upload and before the release script.
- [x] Pass values through stdin, never SSH argv or logs.

### Task 4: Documentation and decision record

**Files:** Create `docs/claude-code.md` (+ English); modify `docs/deployment.md` (+ English), `docs/README.md` (+ English), `plans/deploy-aliyun-playbook.md`, `scripts/doc-budgets.manifest.json`, and the Agent Note.

- [x] Document the three secrets, permissions, verification, and rollback.
- [x] Register the new resident document and budgets.
- [x] Record the runner-download / user-level extraction / apiKeyHelper trade-off.

### Task 5: Verification

- [x] `bash -n deploy/fetch-claude-code-deb.sh`
- [x] `python3 -m py_compile deploy/install-claude-code.py`
- [x] `pnpm test:api -- tests/deploy`
- [x] `pnpm verify:flow`, `pnpm verify:docs`, `pnpm test:gates`, `pnpm lint:api`, `pnpm typecheck:api`
- [ ] Real `claude -p` smoke after the user replaces the placeholder MiniMax key and the PR is merged.
- [ ] Production `Deploy` run; no UI change, so prototype/computer-use comparison is not applicable.
