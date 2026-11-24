# agent-edit patch generation cannot submit an EditPlan under the bare tool surface: unify the edit invocation with analyze

English | [中文](bugfix-claude-edit-tool-surface.md)

```yaml flow
kind: issue
id: bugfix-45
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - apps/api/app/third_party_api/ai_agent/claude_code.py
  - apps/api/tests/**
  - docs/**
  - plans/**
  - .agents/**
adr: [../../notes/implemented/bug-fix/2026-11-24-claude-edit-tool-surface.md]
github:
  number: 566
  url: https://github.com/Shadow-Azure/harness-evolution/issues/566
```

## Background

On 2026-11-24 09:41–09:52 (CST) the production full run `01M85KA28DRPZ9RN26A3GV5JQ2` (skill `codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`) blocked during patch generation in turn 1/3 of step 6/7:

```text
运行在补丁生成（patch）阶段阻塞
claude-code edit call exited unsuccessfully: exit_code=1;
stderr=[claude-code:unrecognized_model] {"model":"MiniMax-M3.1-Flash[1m]","query_source":"sdk"}
```

- Run page: `http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M85KA28DRPZ9RN26A3GV5JQ2`
- `status=blocked`, `blockedStage=patch`, `retryAttempts=0`, `nextRetryAt=null`, failure time `2026-11-24T09:52:30+08:00`.

### Problem statement

The run's durable events (`GET /api/evolution/runs/{id}/events`) give the whole timeline:

| seq | time | event | key fields |
|---|---|---|---|
| 7 | 09:39:24 | `ai_agent_call` `cluster.review` ok | `model=MiniMax-M3.1-Flash[1m]`, `costUsd=0.0509`, `latencyMs=8977`, tokens>0 |
| 8 | 09:39:44 | `ai_agent_call` `cluster.score` ok | same model, `latencyMs=20164`, tokens>0 |
| 9 | 09:41:40 | `ai_agent_call` `severity.score` ok | same model, `latencyMs=115335`, tokens>0 |
| 11 | 09:41:46 | `workspace_prepared` | `cacheHit=true`, `baseCommit=59bebcf`, branch `evo/20261124-01M85KA28DRPZ9RN26A3GV5JQ2` |
| 12 | 09:52:30 | `ai_agent_call` `agent.edit` **error** | `model=unknown`, `costUsd=0`, `sessionId=null`, tokens=0, `latencyMs=0` |
| 13 | 09:52:30 | `run_blocked` | `error.type=AgentProviderError`, `payload.retryable=true`, `stage=candidate` |
| 14 | 09:52:30 | `run_blocked` | `detail=exit_code=1; stderr=[claude-code:unrecognized_model] {"model":"MiniMax-M3.1-Flash[1m]","query_source":"sdk"}` |

Three facts follow directly:

1. **Analyze calls in the same run, with the same model and the same settings, all succeeded** (seq 7–9). `[claude-code:unrecognized_model]` is only the diagnosis line Claude Code prints to stderr for a custom model ID missing from its known list (the official docs list it as a diagnosis line and show `modelOverrides` as the way to silence it). It is not the failure; treating it as one is why triage went the wrong way.
2. **The edit child process actually lived for about 644 seconds** (09:41:46 → 09:52:30). That is neither `could not start` (milliseconds) nor `cancelled` (timeout/cancel takes a different classification), and it is far below `EDIT_TIMEOUT_SECONDS=1800`. The CLI started normally, ran a long conversation, and exited with `exit_code=1` on its own.
3. **The call produced nothing usable**: `AgentUsage` is all zeroes, `sessionId=null`, `model=unknown`, and the submitted `EditPlan` file does not exist, so patch generation failed and the run blocked at `stage=patch`.

### Root-cause analysis process

1. **Read the production evidence**: the error comes from `ClaudeCodeProvider._call()`'s `claude-code {phase} call exited unsuccessfully` branch (`claude_code.py:477-483`) with `phase="edit"`; `detail` is built by `_diagnostics(result)`, which concatenates only `exit_code` and a **bounded stderr** (`claude_code.py:1019-1025`). The CLI's JSON stdout (the `--output-format json` result document) is dropped entirely on this path.
2. **Read the edit argv**: `_edit_argv()` (`claude_code.py:581-612`) still passes `--bare … --allowed-tools Read,Grep,Glob,Write(./.harness-evolution/edits.json5)`; the allow rule comes from `SubmissionPrep.allowed_tools`, always derived as `Write(./<relative>)` (`submission.py:262`), and `collect()` reads only that one file (`submission.py:267-296`).
3. **Compare with the analyze path already fixed in this repo**: the submission tool surface was fixed once in #537 (commit `de7128c9`). `_analyze_argv()` now passes `--safe-mode --restricted --strict-mcp-config --tools Read,Write --allowed-tools Read(//<abs>),Edit(//<abs>) --output-format stream-json --verbose`, and `_ensure_submission_tool()` fails immediately when `system/init.tools` lacks `Write`. That Agent Note states explicitly that "the edit channel is outside this issue's contract and its argv stays unchanged", and `bugfix-cluster-review-file-submission` lists "the edit tool surface still needs its own verification" as a non-goal.
4. **Tool surface**: #537 measured on the same deployment host and the same CLI `2.1.323` that `--bare` narrows the tool set to `Bash/Edit/Read`, with **no `Write`**, and that `--bare --tools "Read,Write"` returns only `Read`, so the tool cannot be added back. The edit path passes `--bare` too, so it cannot write the submission file either.
5. **Permission rule**: even without `--bare`, `Write(./relative)` does not participate in Claude Code's file-write permission matching — file writes are governed only by `Edit(path)` rules and must match the absolute path of the call. #537's control experiment already proved both halves of "relative path + Write rule" are unusable.
6. **Why exit 1 after 644 seconds**: with no usable write tool the model can only retry `Bash`/`Edit` calls denied by `dontAsk` or keep reading files until `--max-turns 40` is exhausted; in print mode an exhausted turn budget ends as an `is_error=true` result and the CLI exits 1. The exact `subtype` (`error_max_turns` or another) cannot be observed today precisely because step 1's stdout was dropped. Regardless of which subtype it was, **without a write tool `edits.json5` can never be written, so this channel must fail**; the 644 seconds is only the shape that failure took.
7. **Ruled out**: model and gateway are fine (three analyze calls on the same model succeeded); credentials are fine (analyze authenticated); the workspace is fine (seq 11 `cacheHit=true`); it is not a timeout (644s < 1800s and the call was not classified `cancelled`); it is not a start failure (`could not start` happens within milliseconds and carries a different detail).

### Conclusion

- **Immediate cause**: the edit call produced no `.harness-evolution/edits.json5`; the model exhausted `--max-turns 40` and the CLI exited 1 with `is_error`. The provider normalized that into `exited unsuccessfully`, patch generation failed, and the run blocked at `stage=patch`.
- **Root cause**: the `ClaudeCodeProvider` edit channel still carries the two defects #537 found before it fixed analyze: (1) `--bare` leaves the tool set without `Write`; (2) the submission allow rule is the relative `Write(./…)`, while the CLI matches file writes only against `Edit(absolute path)`. Analyze was fixed; edit was explicitly left untouched and never ran a real-CLI smoke test.
- **Why it looked like a model problem**: on a non-zero exit `_call()` drops the stdout result and reports stderr only, and `unrecognized_model` is the only line written to stderr, so a diagnosis line impersonated the error cause and also hid the real shape of the failure (four zeroes plus 644 seconds).
- **Capacity defect (handled separately from the root cause)**: `EDIT_MAX_TURNS=40` is too tight for a real edit session — the 644 seconds in this run were 40 turns at roughly 16 seconds each. Once the tool surface works, exploration plus plan writing will still exceed 40 turns, so the turn budget must rise with it; raising the cap never substitutes for the tool-surface fix, because with no usable write tool more turns only stretch the failure to the wall-clock limit.

## Goals

- Make the edit channel genuinely work on the production CLI: the model sees and can call a write tool, the permission rule matches this workspace's submission path, and `edits.json5` is written and collected by `submission.collect`.
- Make edit share **one already-verified invocation shape** with analyze — one subclass-private `_headless_argv()`, one rule builder, one failure-evidence path — instead of maintaining a second argv and a second permission rule set.
- Keep the other call sites (`health_check()`, `run_skill()`) as documented exceptions that still reuse the adapter rules: binary resolution, settings resolution, and failure evidence.
- Make edit failures diagnosable within seconds: a missing `Write`, a denied submission path, or an exhausted turn budget must each name its cause instead of costing 644 seconds and returning one model diagnosis.
- Raise the edit turn budget to what a real session needs (`EDIT_MAX_TURNS` 40 → 120) while keeping `EDIT_TIMEOUT_SECONDS=1800` as the wall-clock cap, so spend protection is not removed.
- Production acceptance: a real full run reaches candidate in step 6 with `agent.edit` at `outcome=ok`, tokens>0, and a model other than `unknown`.

## Design authority

- [07 §5.5.1 AI Agent capability surface](../../../plans/fullstack-design/07-backend-implementation.md): the tool surface and permission mode belong to the provider adapter, not the business layer, and one capability should look the same inside one subclass.
- [07 §5.5.3 six-layer JSON reliability](../../../plans/fullstack-design/07-backend-implementation.md): one-shot task directory + a single write tool + strict/JSON5/repair parsing + Pydantic validation is the cross-backend submission contract; `collect()` reads that one file.
- [07 §5.5.4 execution flow and safety gates](../../../plans/fullstack-design/07-backend-implementation.md): read-only exploration, EditPlan submission, deterministic application on a scratch mirror, and the `--max-turns` spend guard.
- [#537 fix record (Agent Note)](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/bug-fix/2026-11-23-claude-analyze-tool-surface.md): the three measured conclusions — `--bare` has no `Write`, `Write(relative)` does not match, and `Edit(absolute)` is required — plus analyze's final argv shape.
- [Claude Code model configuration docs](https://code.claude.com/docs/zh-CN/model-config): `[claude-code:unrecognized_model]` is a diagnosis line for a custom model ID, silenceable with `modelOverrides`, and unrelated to a call failure.

## Implementation

**The single recommended solution: let edit reuse analyze's already-verified invocation shape and failure-evidence chain, and raise the turn budget to what a real session needs.** It is one change; the four parts cannot be split:

1. **argv and tool surface**: drop `--bare` from `_edit_argv()` and use the same hardening as `_analyze_argv()` — `--safe-mode --restricted --strict-mcp-config`, with `--tools Read,Write` reducing the built-in set to "read the workspace + write the submission file"; replace `--output-format json` with `stream-json --verbose` so `system/init.tools` and the result's `is_error`/`subtype`/`num_turns`/`stop_reason`/`permission_denials` are observable; keep `--no-session-persistence`, `--permission-mode dontAsk`, and `--settings` as they are; `--max-turns` rises per part 4. `Grep`/`Glob` join `--tools` only after the init tool list proves they exist (the Linux default set does not include them); never guess through the allowlist.
2. **Submission permission**: stop feeding `prep.allowed_tools`' `Write(./…)` into the edit `--allowed-tools`; build `Edit(//<abs>/.harness-evolution/edits.json5)` from `prep.result_path` (reusing `_permission_rule_path()`) and `Read(//<abs>)` for the paths that must be read. `submission.py`'s schema/collect/retry contract stays untouched; only the provider adapter's rule construction changes.
3. **Failure evidence**: on `returncode != 0`, `_call()` first assembles detail from the parsed result — `is_error`/`subtype`/`api_error_status`/`num_turns`/`stop_reason`/`permission_denials` — then appends bounded stderr; reuse `_ensure_submission_tool()` to raise within seconds (`retryable=false`) when `system/init.tools` lacks `Write`, instead of burning all 40 turns. `_diagnostics()` no longer treats stderr as the only evidence.
4. **Turn budget**: raise `EDIT_MAX_TURNS` from 40 to 120 (the constant is at `claude_code.py:101`, used by the argv at `:605`). Forty turns are too few for a real edit session — this run's 644 seconds were 40 turns at about 16 seconds each; 120 turns would be about 32 minutes at the same pace and therefore hit the **unchanged** `EDIT_TIMEOUT_SECONDS=1800` first, so the wall clock stays the primary guard and the turn cap becomes a safety net: a healthy session has ample headroom, and a degenerate one is still bounded by SIGINT→SIGKILL at 1800s. Raising the cap only adds capacity and never substitutes for parts 1 and 2 — with an unusable tool surface more turns still cannot produce the submission file.

**Unified invocation shape (one subclass-private function)**: collect the headless `-p` shape into `ClaudeCodeProvider._headless_argv()`; `_analyze_argv()` and `_edit_argv()` only assemble their parameter differences and never hand-build argv again:

| call site | today | treatment |
|---|---|---|
| analyze `_analyze_argv()` | already #537's hardened shape | call `_headless_argv()`: task-directory cwd, `--tools Read,Write`, one-shot submission path |
| edit `_edit_argv()` | still the old `--bare` shape | call `_headless_argv()`: workspace cwd, same submission rules, `--max-turns 120` |
| `health_check()` | runs `--version` only | stays an exception: no prompt, so the `-p` shape does not apply; keeps sharing `_binary()` / `_settings_file()` |
| `run_skill()` (`claude_skill.run`) | bwrap/sandbox-exec + `--bare --session-id --output-format json --permission-mode bypassPermissions` | stays an exception: its contract is the sandbox, private HOME, fixed session, and stdout result; shares `_binary()` / `_settings_file()` and failure evidence only |

`_headless_argv()` owns: binary, `--safe-mode --restricted --strict-mcp-config`, `-p <prompt>`, `--output-format stream-json --verbose`, `--permission-mode dontAsk`, `--tools`, `--allowed-tools`, `--no-session-persistence`, optional `--max-turns`, and optional `--settings`. `_submission_rules()` builds the absolute `Read(//…)` / `Edit(//…)` rules once, and `_call()` normalizes failure evidence once. Neither caller may hand-build these again — edit keeping `--bare` long after analyze was fixed is exactly the structural consequence of having no single constructor.

Why the skill path is not folded in: its `--bare` is part of "load no user configuration" inside the sandbox, and it writes its conclusion to stdout, so it needs no `Write`; forcing analyze/edit's `--restricted` + `--tools` onto it would change or weaken its isolation contract. The goal is one set of provider-adapter rules (binary, settings, tool-surface construction, permission rules, failure evidence), not one argv for every call. edit's read surface follows the same rule builder: the submission write uses the absolute `Edit(//<abs>/.harness-evolution/edits.json5)`, workspace reads use a directory-scoped absolute `Read(//<abs workspace>/…)` rule whose exact syntax is pinned by the deployment-host evidence in implementation step 1, and it may never widen to whole-disk reads.

Supporting tests and docs:

- Unit tests: assert the edit argv has no `--bare`, carries `--safe-mode/--restricted/--strict-mcp-config`, includes `Write` in `--tools`, uses an absolute `Edit(//…)` allow rule, uses `stream-json`, and passes `--max-turns 120`; cover fast failure when `Write` is missing and detail that carries the result's `subtype`/`num_turns` on a non-zero exit; assert analyze and edit profiles through the same `_headless_argv()` so the common segment exists only once.
- Real-CLI e2e: extend #537's opt-in smoke to the edit channel (write succeeds and is collected; an out-of-scope write is denied) and run it on the deployment host with `HE_AI_AGENT_CLAUDE_E2E=1`.
- Docs: update `docs/claude-code.md` with the edit tool surface, permission rule, and acceptance command; the implementing PR adds an owning Agent Note and backfills this issue's `adr`.

## Implementation steps

1. Capture evidence on the deployment CLI first: whether the new edit argv's `system/init.tools` includes `Write`, and whether the `Edit(//<abs>)` rule lets `edits.json5` be written; paste the commands and output into the PR.
2. Extract `_headless_argv()` and `_submission_rules()`: switch `_analyze_argv()` to the shared constructor, bring `_edit_argv()` to the same shape (no `--bare`, hardened flags, `stream-json`, absolute rules), and raise `EDIT_MAX_TURNS` from 40 to 120.
3. Change `_call()`: keep result evidence on a non-zero exit, and wire the edit path into `_ensure_submission_tool()` for fast failure.
4. Add the unit tests and the opt-in real-CLI e2e (no new CI workflow); update `docs/claude-code.md` and the Agent Note.
5. After deployment, accept with a real run: step 6 `agent.edit` is `ok`, tokens>0, model is not `unknown`, and the run proceeds through candidate/push/eval.

## Dependencies and boundary

- Dependencies: none (#537's analyze fix is already on main; edit reuses it).
- Delivery boundary: production code only in `apps/api/app/third_party_api/ai_agent/claude_code.py` (the `ClaudeCodeProvider` subclass); tests in `apps/api/tests/**`; docs in `docs/**`, `plans/**`, `.agents/**`. Do not touch the `AIAgentProvider` base, `submission.py`, `claude_cli.py`, `Settings`/`config.py`, `deploy/**`, or workflows.
- This issue describes the implementation contract only; implementation and verification land in a follow-up PR whose title and commits carry this issue number.

## Verification

```sh
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm lint:api
pnpm typecheck:api
pnpm verify:flow

HE_AI_AGENT_CLAUDE_E2E=1 \
HE_AI_AGENT_CLAUDE_BIN=/opt/harness/shared/claude-code/current/usr/bin/claude \
  pnpm test:api -- tests/test_ai_agent_claude_code.py -k e2e_real_cli
```

- Unit tests and static checks are green; the edit argv contains no `--bare`, `--tools` includes `Write`, the allow rule is an absolute `Edit(//…)`, and `--max-turns` is 120.
- Both analyze and edit profiles are asserted through the same `_headless_argv()`: the shared segment (hardened flags, `stream-json`, `dontAsk`, `--settings`) is produced once, and the only differences are `--tools`, the rules, `--max-turns`, and cwd.
- `EDIT_TIMEOUT_SECONDS` stays 1800: with the larger turn budget the wall clock remains the only hard cap, so a degenerate session cannot run longer than before.
- Real-CLI e2e: the edit smoke writes `.harness-evolution/edits.json5` within 60s and `collect` accepts it; an out-of-scope write is denied; the missing-`Write` case fails within seconds with `tools=…` in its detail.
- Production acceptance: launch a real run and check `agent.edit` through `/api/evolution/runs/{id}/events`: `outcome=ok`, `inputTokens+outputTokens>0`, `model != "unknown"`, `submissionRounds>=1`; the run reaches step 6 candidate and continues into push/eval.

## Acceptance

- The production edit call writes and collects an EditPlan; `ai_agent_call` for `agent.edit` is `outcome=ok` with tokens>0 and a model other than `unknown`.
- Edit and analyze share one hardening set and one absolute `Edit(//…)` submission rule; `--bare` no longer appears in any provider argv.
- Both edit and analyze argv come from the same `_headless_argv()`; `claude_code.py` holds no second place that hand-builds a `-p` headless argv.
- A missing `Write` or a denied submission path fails within seconds and names the missing tool or denied path, instead of 644s plus one model diagnosis.
- A non-zero exit carries the CLI result's structured evidence (`subtype`/`num_turns`/`stop_reason`/`permission_denials`) in its detail; a stderr diagnosis line no longer impersonates the cause.
- A healthy edit call on the production workload does not end in `error_max_turns`; `ai_agent_call` records the real `num_turns`, and the 120-turn budget still bottoms out at the unchanged `EDIT_TIMEOUT_SECONDS=1800`.
- Permissions stay minimal: Bash, writes outside the workspace, and undeclared tools are denied; `submission.py` and the base contract are unchanged.
- The real-CLI e2e remains repeatable on the deployment host as an opt-in run (no new CI workflow).

## Gates and CI

- `pnpm test:api`, `pnpm lint:api`, `pnpm typecheck:api`, `pnpm verify:flow`, `pnpm verify:flow-online`.
- CI lanes: `api-static`, `unit-tests-api`, `docs-flow`, `flow-online`; the real-CLI e2e runs on the deployment host behind an opt-in environment variable and is not part of CI.

## Non-goals

- Do not replace the submission channel with `--json-schema` or another Claude Code-only structured output; the file channel must stay.
- Do not widen permissions (no global `Write`, no Bash-written submission file), and do not use a larger `--max-turns` as a substitute for the tool-surface fix. This issue raises the turn cap from 40 to 120 as requested but leaves `EDIT_TIMEOUT_SECONDS` unchanged.
- Do not change the edit prompt, EditPlan semantics, the deterministic applier, evaluation, or the UI.
- Do not fold `health_check()` or `run_skill()` into `_headless_argv()`: the first has no prompt, and the second has its own contract (sandbox, private HOME, fixed session, stdout result); they only share binary / settings / failure evidence.
- Do not change the `AIAgentProvider` base, `submission.py`'s submission contract, the `claude_cli.py` shared transport, `Settings`/`config.py`, or the deployment workflow.
- Do not write production credentials, Session content, or private data into the repo, and do not open a new milestone for a single problem.
