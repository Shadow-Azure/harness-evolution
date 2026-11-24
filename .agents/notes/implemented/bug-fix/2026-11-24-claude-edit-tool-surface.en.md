# Agent Note: Claude Code edit submission surface and unified invocation shape

Status: implemented

English | [中文](2026-11-24-claude-edit-tool-surface.md)

## Problem

The production full run `01M85KA28DRPZ9RN26A3GV5JQ2` blocked at the patch stage: the `agent.edit` child process lived about 644 seconds and then exited with `exit_code=1`, `AgentUsage` was all zeroes, `sessionId=null`, `model=unknown`, and `.harness-evolution/edits.json5` did not exist. The root cause is the same one #537 fixed for analyze: the edit channel still passed `--bare` (tool set `Bash`/`Edit`/`Read`, no `Write`), and its submission rule was the relative `Write(./<relative>)`, while Claude Code matches file writes only against absolute `Edit(path)` rules. Without a write tool the model can only retry `Bash`/`Edit` calls denied by `dontAsk` until `--max-turns 40` is exhausted; on a non-zero exit the provider also dropped the stdout result and reported stderr only, so the `[claude-code:unrecognized_model]` diagnosis line impersonated the cause and the 644-second turn-exhaustion shape stayed invisible.

## Decision

Edit and analyze share one headless constructor, `_headless_argv(_HeadlessProfile)`: binary, `--safe-mode`, `--restricted`, `--strict-mcp-config`, `-p`, `--output-format stream-json --verbose`, `--permission-mode dontAsk`, `--tools`, `--allowed-tools`, `--no-session-persistence`, optional `--max-turns`, and `--settings` are assembled only there; `_analyze_argv()` and `_edit_argv()` assemble nothing but their profile differences (prompt, tool set, rules, turns). One rule builder, `_submission_rules()`, produces the submission write as the absolute `Edit(//<abs edits.json5>)` in both phases; analyze's read surface is `Read(//<task>/schema.json)` and edit's is the tree-scoped `Read(//<workspace>/**)`.

The tool surface is pinned per phase as constants: `ANALYZE_TOOLS = ("Read", "Write")` and `EDIT_TOOLS = (*READ_ONLY_TOOLS, SUBMISSION_TOOL)`, i.e. `Read,Grep,Glob,Write`. `Bash` and the `Edit` tool never appear; edit explores with read-only tools and the submission file is its only write.

`EDIT_MAX_TURNS` rises from 40 to 120 while `EDIT_TIMEOUT_SECONDS=1800` stays. Forty turns are too few for a real session (this run's 644 seconds were about 40 turns at 16 seconds each); at the same pace 120 turns would be about 32 minutes and therefore hit the 1800s wall clock first, so the wall clock remains the primary guard and the turn cap becomes a safety net: a healthy session has headroom, and a degenerate one is still stopped by SIGINT→SIGKILL at 1800s.

Failure evidence is unified in `_call()`: a non-zero exit reports the result's structured fields first (`is_error`/`subtype`/`api_error_status`/`tools`/`stop_reason`/`num_turns`/`permission_denials`) and then bounded stderr; a `system/init.tools` set without `Write` fails as soon as the call ends (`retryable=False`) on both the zero-exit and non-zero-exit paths, with no retry, while detecting it in flight would need a streaming transport that is out of scope; and a failed edit `collect` merges the `permission denied:` path into the detail instead of reporting only `missing`.

Deployment-host evidence (CLI 2.1.325, `/opt/harness/shared/claude-code/current/usr/bin/claude`, service user `harness`) pinned the three implementation premises: `--tools Read,Grep,Glob,Write` reports `system/init.tools` as `Glob,Grep,Read,Write` (Linux really does provide `Grep`/`Glob`); an `Edit(//<abs>)` rule can write the submission file, and the CLI creates the `.harness-evolution/` directory itself; the tree-scoped `Read(//<abs workspace>/**)` rule is accepted, with 6 turns and 0 denials. `health_check()` (only `--version`, no prompt) and `run_skill()` (sandbox, private HOME, fixed session, stdout result) stay exceptions that reuse only `_binary()`, `_settings_file()`, and the failure-evidence normalization.

## Alternatives considered

- **Write a second argv for edit**: exactly this path let edit keep `--bare` long after analyze was fixed; two argvs mean two permission surfaces that drift. Rejected.
- **`Write(//<abs edits.json5>)` rule**: the real CLI's file-write permission matches only `Edit(path)`; `Write(path)` rules do not participate. Infeasible.
- **Only raise `--max-turns`**: with an unusable tool surface more turns still cannot produce the submission file and only stretch the failure to the wall-clock limit. Rejected.
- **Fold `run_skill()` into `_headless_argv()`**: it would weaken its sandbox and stdout contract; `health_check()` has no prompt and does not fit the `-p` shape. Both stay exceptions.
- **Switch to `--json-schema` native structured output**: it binds submission to a Claude Code-only channel and breaks the provider-neutral contract; the file channel stays.

## Consequences

- Edit can write `.harness-evolution/edits.json5` and have it collected on CLI 2.1.325; the opt-in real-CLI e2e covers both a successful write and a denied out-of-scope write, run on the deployment host with `-k e2e_real_cli`.
- `--bare` no longer appears in any analyze/edit argv; a new edit call site must go through `_headless_argv()`, or a unit test will see a second copy of the common segment.
- `stream-json --verbose` stdout is larger than a single JSON document and remains bounded only by the process timeout and memory; failure details never print model prose.
- Edit's 120-turn budget is a capacity guarantee for healthy sessions only; the real cost ceiling is still the 1800s wall clock. CLI upgrades must preserve `--tools`, the `Edit(path)` permission semantics, and flags such as `--restricted`.
