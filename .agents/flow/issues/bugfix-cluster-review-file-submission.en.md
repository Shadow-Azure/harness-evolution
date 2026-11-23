# Make the cluster.review file submission channel usable under the real CLI

English | [中文](bugfix-cluster-review-file-submission.md)

```yaml flow
kind: issue
id: bugfix-31
milestone: bugfix
depends:
  - bugfix-17
  - bugfix-26
  - bugfix-28
priority: P2
status: ready
scope:
  - apps/api/app/third_party_api/ai_agent/claude_code.py
  - apps/api/tests/**
  - tests/e2e/**
  - docs/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-23-claude-analyze-tool-surface.md
github:
  number: 537
  url: https://github.com/Shadow-Azure/harness-evolution/issues/537
```

## Background

On 2026-11-23 between 16:02 and 16:37, three consecutive production full runs failed at the clustering stage with the same error: `cluster cluster.review failed: AgentProviderError: claude-code analysis call was cancelled`.

| run | started (CST) | AI call duration | submission rounds | result |
|---|---|---|---|---|
| `01M83PVC3WEHGKDHPYSXWFN19N` | 16:02:39 | 419.378s | first call returned after ~119s with `submissionRounds=1` and `parseFailures=1`; the feedback retry was killed at 300s | failed |
| `01M83QN546PEXT1VFFDKVMXSKH` | 16:16:44 | 300.362s | `submissionRounds=0`; the first call alone hit the timeout | failed |
| `01M83RHMTRXVYC1KR0BJM4WFNT` | 16:32:17 | 300.363s | `submissionRounds=0`; the first call alone hit the timeout | failed |

Every `ai_agent_call` reports `task=cluster.review`, `outcome=error`, `model=unknown`, `inputTokens=0`, and `outputTokens=0`; `run_failed.error.stage=cluster`. In the 16:02 run the first call did return, but no parseable `result.json5` existed; the designed single feedback retry then ran into the 300s cap and was terminated via SIGINT→SIGKILL. In the 16:16 and 16:32 runs the first call already burned the full 300s.

### Problem statement

The submission channel asks the model to write its conclusion into `./result.json5` inside the per-call task directory, and the provider allows exactly one write tool, `Write(./result.json5)`. The deployed CLI is Claude Code `2.1.323`, and the analyze argv also passes `--bare`; bare mode narrows the available tools to `Bash / Edit / Read`, with **no `Write`**. The model cannot produce the submission file, so it either attempts `Bash`/`Edit` (both denied by `dontAsk`) or gives up, and the file is always missing. That missing file triggers the single feedback retry, which faces the same unusable tool face and finally hits `ANALYZE_TIMEOUT_SECONDS = 300`, classified as `cancelled`.

None of this is about the process, permissions, model, or network: the CLI starts (issue #533 fixed the 0700 directory) and the model returns a normal turn; the failure point is the submission tool face and the permission rule.

Why the file channel must stay: `submission.py` is the provider-independent contract (schema + `result.json5` + collect + one feedback retry). Later deployments may switch to other AI agents/CLIs whose tool names, permission models, and structured-output capabilities differ widely; binding analyze to Claude Code's `--json-schema` would make the channel non-portable. This issue therefore keeps the file channel and only fixes the provider-side CLI adaptation.

### Root-cause analysis

1. **Read the three failed runs' events**: `latencyMs` is 419378 / 300362 / 300363, `submissionRounds` is 1 / 0 / 0, and `submissionParseFailures` is 1 / 0 / 0. The failure follows the `AI call: cluster.review (error)` event and is recorded as `run_failed` with `stage=cluster`. The pause requests in the 16:16 and 16:32 runs arrived 2–45 seconds after the call started, yet failures still occurred exactly 300s after the call started; pausing does not cancel an already-started analyze child, so it is ruled out.
2. **Compare with the runs before #533**: the 10:40 and 14:06 runs each had three `could not start` calls (7–10ms, 0 tokens) and still completed under the degrade policy; the 14:22 run surfaced the same `could not start` under strict. The “CLI cannot start” failure predates this error and is the 0700 permission defect; only after #533 did the failure move to the submission stage.
3. **Read the deploy logs**: Deploy `45133432394` (15:45) installed and configured Claude Code `2.1.323`; the shared settings and `current` symlink passed the other-bit preflight; the `sudo -u harness` smoke was skipped for lack of permission. The 16:08 / 16:23 deploys shipped `8db62923` / `6d473733` with the same CLI version.
4. **Read the code**: `claude_code._analyze_argv()` builds `--bare … --allowed-tools Write(./result.json5) --no-session-persistence`; `submission.prepare()` writes `./schema.json` and asks the model to read it and write the conclusion to `./result.json5`; `collect()` reads only that file. `--allowed-tools` is an allowlist, not a tool provider; when a tool is absent from the tool set, no allowlist entry can help. The prompt also asks the model to read `./schema.json`, but the allowlist has no `Read`: a second gap in the same tool face.
5. **Reproduce with the same CLI version**: launching `2.1.323` locally with the same argv and reading the `system/init` event (the tool list is decided by the CLI, not the model) gives `tools=["Bash","Edit","Read"]`; removing `--bare` makes `Write` appear; `--bare --tools "Read,Write"` returns only `Read`, so `Write` cannot be added back. With the full analyze-shaped prompt the CLI exits 0 after ~25.7s, `result.json5` does not exist, `permission_denials` records the denied `Bash` and `Edit`, and the model's final text explicitly says “the current tool set has no Write tool”. A non-bare control shows the model does attempt `Write`, but the `Write(./result.json5)` rule does not match the task directory's absolute path, so the write is still denied; that control ran on macOS where `/tmp` is a symlink, so the final rule must be verified on the target Linux host.
6. **Check the review and acceptance history**: PR #514's review discussion point 5 already called out “analyze only allows Write while the prompt asks the model to read schema; the `Write(./…)` pattern has not been verified against the real CLI”, and the conclusion was to defer it to the deployment host. The real-CLI e2e is opt-in via `HE_AI_AGENT_CLAUDE_E2E=1` and never runs in CI; unit tests use a MockRunner that writes `result.json5` itself and cannot see the real tool face. Issue #521 and PR #533 both require a real run whose `cluster.review` is `outcome=ok`, yet production has never had a single successful call, so that acceptance was never actually exercised.

### Conclusion

- Direct cause: the `cluster.review` analyze call never produces a parseable submission; the single feedback retry after the first failure runs into `ANALYZE_TIMEOUT_SECONDS = 300`, is terminated by a process-group SIGINT→SIGKILL, normalized to `cancelled`, and strict policy turns `ClusterAIFailure` into a failed run.
- There are two root causes and both must be fixed: (1) `--bare` removes `Write` from the CLI tool set, so the file channel cannot work; (2) relative rules such as `Write(./result.json5)` do not match the per-call task directory's absolute path, and `Read` is not allowlisted, so the schema is invisible too.
- #533 is a necessary fix, not the culprit; #526 turned the same failure from a silent degradation into an explicit failure; #514 introduced the latent defect “the file channel depends on Write but the tool face was never verified”.
- The chosen solution: keep the file channel; fix the tool face and the permission rule only inside the `ClaudeCodeProvider` subclass; make “tool unavailable” fail fast and diagnosably instead of burning 300s. `--json-schema` is not used.

## Goals

- Make the file submission channel actually work on the deployed CLI `2.1.323`: the model can see and call the write tool, and the permission rule matches the task directory of the current call; **production changes are confined to the `ClaudeCodeProvider` subclass**.
- Keep the submission semantics provider-independent: the `schema.json`, `result.json5`, collect, and one-feedback-retry contract stays; only the provider adaptation layer may adjust argv and tool/permission rules per CLI.
- When the submission tool is missing or denied, emit a diagnosable failure within seconds (naming the missing tool or the denied path) instead of entering the 300s retry; preserve bounded stdout/stderr and `permission_denials` on timeout/cancellation.
- Production acceptance: a real run's `cluster.review` is `outcome=ok`, tokens>0, and model is not `unknown`; `cluster.score` and `severity.score` are also ok; the run reaches step 6/7.

## Design authority

- [07 §5.5.1 AI Agent capability surface](../../../plans/fullstack-design/07-backend-implementation.md): analyze is the stable capability surface; tool faces and permission modes belong to the provider adaptation layer and must not leak into the business layer.
- [07 §5.5.2 Three-layer clustering and task keys](../../../plans/fullstack-design/07-backend-implementation.md): `cluster.review` / `cluster.score` / `severity.score` share the analyze path, so one fix covers all three tasks.
- [07 §5.5.3 Six-layer JSON reliability](../../../plans/fullstack-design/07-backend-implementation.md): the one-shot task directory + `Write(./result.json5)` + strict/JSON5/repair ladder + Pydantic validation + one feedback retry is the cross-backend submission contract.
- [2026-11-22 real-AI design note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/feature/2026-11-22-evolution-real-ai-design.md): the `--bare` authentication/minimalism trade-off, `--no-session-persistence`, and timeout/cancellation normalization.
- [PR #514 review: discussion point 5](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/2026-11-22-pr514-review.md): the original record that the tool face was never verified; this issue changes “deferred” to “must fix”.
- [Claude Code deployment doc](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/claude-code.md): shared settings, CLI version, and the `ANTHROPIC_API_KEY` deployment boundary.

## Implementation

**Hard constraint (requested 2026-11-23)**: production changes are confined to the `ClaudeCodeProvider` subclass (`apps/api/app/third_party_api/ai_agent/claude_code.py`). Do not modify the `AIAgentProvider` base class, the `submission.py` channel, the `claude_cli.py` shared transport, `Settings` / `config.py`, `deploy.yml`, or any workflow. The launch mode is fixed inside the subclass argv and adds no deployment configuration; switching environments or AI agents uses the existing `AI_AGENT_PROVIDER` to select a different subclass, with CLI details encapsulated in each subclass. Tests, e2e, and docs may change as required by acceptance. If the subclass cannot complete the fix independently (for example, a shared-layer change becomes necessary), stop and report instead of widening the change.

- **Tool face (first fix)**: on the pinned CLI `2.1.323`, establish a launch mode that both keeps `Write` and preserves the minimal context/permissions. Candidates:
  - Drop `--bare` inside the subclass argv and preserve the hardening it provided with explicit flags/environment variables (disable hooks/plugins/CLAUDE.md auto-discovery, disable the auto-updater, and so on), then verify that the init tool list contains `Write`; add no deployment configuration;
  - If the CLI offers no equivalent “minimal mode with Write”, record that CLI limitation in the provider adaptation layer and switch to a file-write path that pre-creates an empty `result.json5` and allows `Read/Edit`, provided the Edit creation semantics are verified on the same real CLI version;
  - Do not globally allow `Write` and do not use Bash to write the submission file.
- **Permission rule (second fix)**: build rules from the current call's absolute `prep.directory`; at minimum allow `Read(<abs>/schema.json)` and `Write(<abs>/result.json5)` (or a directory glob), keep `dontAsk`, and continue to deny Bash, Edit (unless it becomes the verified creation path), and writes outside the task directory. The exact absolute-path / `//` prefix / glob syntax must come from a real-CLI verification recorded in the PR.
- **Fast failure and evidence (all inside the subclass)**: parse `permission_denials`, `stop_reason`, and `num_turns` from the CLI result; when the submission tool is absent from the tool set or the write is denied, raise an `AgentProviderError` with the concrete reason immediately (no retry, no 300s wait). On timeout/cancellation, keep a bounded tail of stdout/stderr so `detail` is no longer just `cancelled`; the shared transport already retains stderr, and the subclass only writes it into the diagnosis without touching the transport.
- **Tests**: unit tests for argv/rule construction, fast failure when the tool is missing, and diagnosis details for a denied write; a real-CLI e2e for both “write succeeds and is collected” and “out-of-scope write is denied”; the e2e stays opt-in and runs on the deployment host, with no CI workflow change.
- **Docs and note**: update `docs/claude-code.md` with the analyze tool face/permission rules and verification commands; the implementation PR adds the owning Agent Note and backfills this issue's `adr`.

## Implementation steps

1. Reproduce on `2.1.323` and pin the evidence: init tool list, tool list without bare (or an equivalent mode), and permission-rule matching results; paste the commands and output into the PR.
2. Change `claude_code._analyze_argv()` and the tool/rule construction (add no setting; the launch mode is fixed inside the subclass) while keeping the `submission.py` schema/collect/retry contract unchanged.
3. Add the tool-face preflight and fast failure; add `permission_denials`/timeout evidence capture.
4. Add or update unit tests and the real-CLI e2e; run the e2e on the deployment host as an opt-in check (no CI workflow change); update the docs and Agent Note.
5. After deployment, verify with a real run: `cluster.review`, `cluster.score`, and `severity.score` are all `outcome=ok`, tokens>0, model not `unknown`, and the run reaches step 6/7.

## Dependencies and boundary

- Depends on: bugfix-17 (real provider and submission channel), bugfix-26 (strict failure semantics for real providers), bugfix-28 (harness can execute the CLI).
- Boundary: production code is limited to `apps/api/app/third_party_api/ai_agent/claude_code.py` (the `ClaudeCodeProvider` subclass); tests are `apps/api/tests/**` and `tests/e2e/**`; docs are `docs/**`, `plans/**`, and `.agents/**`. Do not change the base class, `submission.py`, `claude_cli.py`, `Settings`/`config.py`, `deploy/**`, or `.github/workflows/**`.
- This issue only defines the implementation contract; implementation and verification happen in a follow-up PR. That PR's title and commits must contain this issue's number.

## Verification

```sh
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm test:api
pnpm lint:api
pnpm typecheck:api

HE_AI_AGENT_CLAUDE_E2E=1 \
HE_AI_AGENT_CLAUDE_BIN=/opt/harness/shared/claude-code/current/usr/bin/claude \
  pnpm test:api -- tests/test_ai_agent_claude_code.py -k e2e_real_cli

pnpm verify:docs
pnpm verify:flow
```

- Unit tests and static checks are green; the real-CLI e2e completes within 60s, `result.json5` is written and passes `collect`, and an out-of-scope write (outside the task directory) is denied.
- A direct probe on the deployment host shows `Write` in the init tool list and no entry for the current write target in `permission_denials`.
- Production acceptance: start a fresh real run and inspect `ai_agent_call` via `/api/evolution/runs/{id}/events`:
  - `cluster.review`: `outcome=ok`, `inputTokens+outputTokens>0`, `model != "unknown"`, no `degraded`;
  - `cluster.score` and `severity.score` are also `ok`;
  - the run proceeds to step 6/7 and no longer stops at `stage=cluster`.

## Acceptance

- A real run's `cluster.review` / `cluster.score` / `severity.score` are all `outcome=ok`, tokens>0, model not `unknown`, and no `degraded` appears.
- The run reaches step 6/7; failures no longer always land at `stage=cluster`.
- When the submission tool is missing or denied, the call fails within seconds and the error detail names the missing tool or the denied path; a 300s `cancelled` is no longer the only information.
- Permissions stay minimal: Bash, Edit (unless it becomes the verified creation path), out-of-task-directory writes, and undeclared tools are all denied.
- The file channel stays provider-independent: no `--json-schema` dependency, and the `submission.py` schema/collect/retry contract is unchanged.
- The real-CLI e2e is repeatable on the deployment host as an opt-in check (no CI workflow change).

## Gates and CI

- `pnpm test:api` (including provider unit tests), `pnpm lint:api`, `pnpm typecheck:api`, `pnpm verify:docs`, `pnpm verify:flow`, `pnpm verify:flow-online`.
- If `Settings` or an API contract changes, add `pnpm contract:check` and `pnpm test:gates`.
- CI lanes: `api-static`, `unit-tests-api`, `docs-flow`, `flow-online`; no CI workflow is added, and the real-CLI e2e runs on the deployment host through an opt-in environment variable.

## Non-goals

- Do not switch analyze to `--json-schema` or any other Claude Code-specific structured-output capability; the file channel must stay.
- Do not revert strict, restore silent degradation, or change `cluster_llm`'s failure semantics.
- Do not widen permissions (no global `Write`, no Bash writes for the submission file, no running the service as the deploy user).
- Do not change the clustering prompts, scoring algorithms, UI, or unrelated providers.
- Do not change the `AIAgentProvider` base class, the `submission.py` contract, the `claude_cli.py` shared transport, `Settings`/`config.py`, or the deployment workflow; do not add a launch-mode setting.
- Do not write production credentials, Session content, or private data into the repository; do not open a new milestone for a single problem.
