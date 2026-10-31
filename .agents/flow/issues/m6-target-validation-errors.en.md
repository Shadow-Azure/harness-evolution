# Target configuration: explain validation failures and surface git output

English | [中文](m6-target-validation-errors.md)

```yaml flow
kind: issue
id: m6-19
milestone: m6
depends:
  - m5-02
  - m5-03
  - m6-07
priority: P1
status: ready
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 185
  url: https://github.com/Shadow-Azure/harness-evolution/issues/185
```

## Background

### What the problem is

The create and edit target dialogs share one form that submits the object name, repository URL, subdirectory, and baseline (`defaultRef`) together. The backend returns a single `422 REPO_INVALID` for any validation failure, with `message` fixed to `repository or ref is invalid` and empty `details`. The frontend replaces every `REPO_INVALID` with the same sentence, “仓库或 ref 无效，请检查地址、子目录与基线”, and renders one `server-error` at the bottom of the form. Users learn that something is wrong but not which field, rule, or fix.

### Symptoms

- The repository URL uses `http://`, embeds a username and password, carries a query/fragment, or has an invalid port, and the dialog shows the same generic error.
- The subdirectory is absolute, contains `..`, or uses backslashes, and the dialog shows the same generic error.
- The baseline contains illegal characters, `..`, or ends with `.` or `/`, and the dialog shows the same generic error.
- The remote repository is unreachable, unreadable, fails DNS, or times out, and the dialog shows the same generic error; the actual `git ls-remote` stderr is discarded in `_run`.
- The baseline branch or tag does not exist remotely (`git ls-remote --exit-code` exit 2), and the failure cannot be distinguished from an unreachable repository.
- The object name is empty, too long, or contains control characters, and the backend still returns `REPO_INVALID` while the copy points users at the repository, subdirectory, and baseline.
- The subdirectory syntax is valid but the directory does not exist, so the save succeeds and the failure appears only during run preparation as `target subdirectory is missing`.

### Impact

- Administrators must guess and retry; the most common URL-format, ref-spelling, and permission problems cannot be located in one pass.
- The sentence mixes three fields, and subdirectory existence is not checked on save, so the copy promises a check that does not exist.
- Remote failures carry no command output, so DNS, TLS, authentication, a missing repository, and a missing ref are indistinguishable.
- Existing tests freeze the generic copy as expected behavior, leaving no field-level regression assertions.

### Root cause

- Three backend collapses: every rule failure in `_normalize_text`, `_validate_sub_dir`, and `_validate_repo_url` raises the same `_repo_invalid()`; `_validate_remote` maps `RepoInvalid` to the same `AppError` with empty `details`.
- `GitProcessResult` already carries `stdout` and `stderr`, but `SubprocessGitRemote._run` raises `RepoInvalid` on a non-zero exit, timeout, or `OSError` without the exit code or output.
- The frontend `targetErrorMessage` branches only on the error code and never reads `ApiError.details`; `TargetFormDialog` receives only a `serverError` string and has no field-level error channel.
- The existing Agent Note treats “without stderr, credentials, or paths” as the security boundary but does not separate “raw output that must not be shown” from “a sanitized excerpt that can be shown”.

### Recommendation

- Keep the `REPO_INVALID` code unchanged; add `field` and `reason` to `details`; map each reason to a specific cause and fix, and anchor the error to its field.
- For remote failures, return the command name, exit code, and a bounded sanitized `output` in `details.command`; only admin create/update returns it, and the member-readable versions endpoint does not.
- Run `output` through the same redaction used for run logs: remove tokens, Bearer values, URL userinfo, private keys, and provider keys; strip control characters; replace local absolute paths; bound by lines and bytes.
- Do not clone the repository on save to check subdirectory existence; state in the form that directory existence is checked when a run starts.
- Cover every reason, remote exit code, and redaction boundary with parameterized tests; cover field anchoring, suggestion copy, the technical output block, and the no-details fallback in the frontend.

## Goals

- `REPO_INVALID` returns a distinguishable `field` and `reason`, and the frontend shows the specific cause and fix under that field.
- When a remote command fails, administrators can see a bounded, sanitized excerpt of the actual git output and its exit code in the dialog.
- Object name, repository URL, subdirectory, and baseline errors no longer share one sentence.
- Responses without `details` still fall back to the current generic copy, preserving compatibility.
- Form copy and documentation state when subdirectory existence is checked and no longer imply a save-time check.

## Design authority

- [plans/fullstack-design/05-api-design.md §4.11](../../../plans/fullstack-design/05-api-design.md#411-进化对象配置仅配置后可自进化): `REPO_INVALID` means the repository or ref is unavailable, and saves and versions share the error.
- [plans/fullstack-design/08-frontend-implementation.md §9.5](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets): required-field validation runs before save; repository, ref, and subDir validity come from the backend as `422 REPO_INVALID`, and the form renders the error.
- [2026-10-27-evolution-target-config.en.md](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-10-27-evolution-target-config.en.md): the current security boundary requires `REPO_INVALID` to exclude stderr, credentials, and paths; this issue narrows it to “admin write endpoints return bounded, sanitized, path-free git output; read endpoints do not”.
- If implementation conflicts, the current `GitRemote` validation semantics and that security boundary take precedence.

## Implementation

- Backend `service/evolution/targets.py`: introduce closed sets for fields and reasons, map each local rule to `field` and `reason`, and keep `422 REPO_INVALID` and the existing message unchanged.
- `field` values: `objectName`, `repoUrl`, `subDir`, `defaultRef`; `reason` values: `object_name_invalid`, `repo_url_format`, `repo_url_credentials`, `sub_dir_format`, `ref_format`, `ref_not_found`, `repo_unreachable`, `git_timeout`, `git_unavailable`.
- Backend `third_party_api/git/remote.py`: `RepoInvalid` carries `reason`, `exit_code`, and `stderr`; timeout maps to `git_timeout`, `OSError` to `git_unavailable`, exit 2 to `ref_not_found`, and any other non-zero exit to `repo_unreachable`; `list_tags` never produces `ref_not_found`.
- Backend `utils/redaction.py`: add a command-output cleaner that reuses `redact_text`, replaces POSIX and Windows absolute paths while preserving URL paths, strips control characters, and keeps the last 40 lines and 4096 bytes.
- Frontend `pages/evolution/targets/Index.vue`: parse `details` and map reasons to `{field, message, suggestion, command}`; fall back to the generic copy and a four-item checklist when the reason is unknown or `details` is absent.
- Frontend `pages/evolution/targets/components/TargetFormDialog.vue`: accept a structured server error, render it under the matching field with `aria-invalid`/`aria-describedby`, focus the first invalid field after a failed submit, clear that error when the field changes, and render an expandable, scrollable monospace output block for command failures.
- Docs and note: update 05 §4.11 with the details shape, 08 §9.5 with field-level errors and the “subdirectory checked at run time” rule, and the Agent Note with the refined stderr boundary.
- Tests: parameterized backend field/reason cases, remote exit codes, redaction, and truncation; frontend reason mapping, field anchoring, the technical output block, and the no-details fallback; update the E2E unreachable-repository assertion.

The added fields leave the error code unchanged; the on-wire shape is:

```json
{
  "error": {
    "code": "REPO_INVALID",
    "message": "repository or ref is invalid",
    "details": {
      "field": "repoUrl",
      "reason": "repo_unreachable",
      "command": { "name": "git ls-remote", "exitCode": 128 },
      "output": "fatal: unable to access 'https://...': Could not resolve host: ..."
    }
  }
}
```

## Implementation steps

1. Add failing tests first: each local rule returns the expected `field`/`reason`; remote exit 2/128, timeout, and `OSError` map to their reasons; sanitized output contains no credentials or local paths.
2. Introduce the `field`/`reason` closed sets in the target service and replace each `_repo_invalid()` call site.
3. Carry the exit code and stderr across the git remote boundary, and assemble `details.command` and `details.output` in the target service.
4. Implement command-output cleaning and truncation in the redaction utility, covering URL-path preservation and local-path replacement.
5. Rework the frontend error mapping, field anchoring, focus/clear behavior, and git output block; add web unit tests and E2E coverage.
6. Update 05/08 and the Agent Note; run focused tests, types, lint, flow, and documentation gates.

## Dependencies and boundary

- Dependencies: m5-02, m5-03, m6-07.
- Delivery boundary: change only the structured detail of target-save errors, the frontend presentation, and related tests; do not change the git invocation, the error-code set, or the run-time subdirectory check.
- Compatibility: `details` is additive; responses and tests without `details` continue to work.

## Verification

```sh
pnpm test:api -- tests/m5-02-target-config-api
pnpm --filter @harness/web exec vitest run src/pages/evolution/targets
pnpm typecheck:api
pnpm typecheck:web
pnpm lint:api
pnpm lint:web
pnpm test:e2e -- "m5 target configuration"
pnpm verify:flow
pnpm verify:docs
```

- Parameterized local-rule cases assert `field` and `reason`, and an empty `details.output`.
- The unreachable case asserts `reason=repo_unreachable`, exit code 128, and an `output` with no token, URL userinfo, or local absolute path.
- The missing-ref case asserts `reason=ref_not_found`, exit code 2, and frontend copy distinct from “repository unreachable”.
- Frontend cases assert the field error, summary copy, git output block, no-details fallback, and clearing after edit.
- All type, lint, E2E, flow, and documentation gates pass.

## Acceptance

- When the repository URL uses `http://`, embeds credentials, carries a query/fragment, or has an invalid port, the `repoUrl` field shows a format or credential error and fix, with no git output block.
- When the subdirectory is absolute, contains `..`, or uses backslashes, the `subDir` field states the relative-path requirement.
- When the baseline contains illegal characters, `..`, or ends with `.` or `/`, the `defaultRef` field shows valid examples.
- When the repository is unreachable, the `repoUrl` field and summary say it cannot be reached, and the technical details show the exit code and sanitized git output.
- When the baseline branch or tag is missing, the `defaultRef` field says the repository is reachable but the ref is not, the technical details show exit code 2, and the generic “check the subdirectory and baseline” sentence does not appear.
- When the object name is empty, too long, or contains control characters, the `objectName` field shows the name rule instead of repository or ref copy.
- The edit and create dialogs behave identically; after a 422 the dialog stays open and preserves input.
- When the server returns no `details`, the frontend falls back to the current generic copy and a four-item checklist.
- The subdirectory help text states “format is checked on save, directory existence is checked when a run starts”.

## Gates and CI

- `pnpm test:api`
- `pnpm test:web`
- `pnpm typecheck:api` / `pnpm typecheck:web`
- `pnpm lint:api` / `pnpm lint:web`
- `pnpm test:e2e -- "m5 target configuration"`
- `pnpm contract:check`
- `pnpm verify:flow`
- `pnpm verify:docs`
- All CI lanes pass and coverage stays at or above 80%.

## Non-goals

- Do not add or rename error codes; `REPO_INVALID` stays stable.
- Do not clone or fetch the repository on save to check subdirectory existence; run preparation keeps that check.
- Do not return raw git output from the member-readable versions endpoint.
- Do not probe arbitrary unsaved `repoUrl` values from the browser.
- Do not persist git output to the database or run events.
- Do not refactor the whole configuration page, launch wizard, or git workspace implementation.
- Do not change the `git ls-remote` argv, timeout, or non-interactive constraints.
