# Attribution bindings hang silently: preflight the runtime and surface its state

English | [中文](bugfix-attribution-runtime-silent-hang.md)

```yaml flow
kind: issue
id: bugfix-32
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/api/app/main.py
  - apps/api/app/service/evolution/local_attribution.py
  - apps/api/tests/**
  - apps/web/src/pages/evolution/targets/**
  - apps/web/src/pages/overview/components/TargetsOverview.vue
  - deploy/**
  - .github/workflows/deploy.yml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - .env.example
  - plans/**
  - .agents/**
adr: []
github:
  number: 544
  url: https://github.com/Shadow-Azure/harness-evolution/issues/544
```

## Background

On 2026-11-23 17:13:08 CST the production frontend bound the system default `attribute-badcases` skill to the evolution object `codespec-subagent-driven-development` (target `01M7Y37ZR7N61GVWMZ31FPN8JY`, workspace `01M7KJ05ENF9784GPBDV544VB0`). The PUT returned 200 and the target row had `attribution_package_id=default-attribute-badcases`, `attribution_generation=01M83TWE7ZSTC6Z5MNF0P0KQDM`, and `attribution_due=attribution_cutoff=2026-11-23 17:13:08`. At 17:39 (DB `NOW()` 17:39:51) it was still `attribution_owner=NULL`, `attribution_failures=0`, `attribution_error=NULL`, `updated_at=17:13:08`; nothing claimed it and no failure retry ran. The service was redeployed to `065a96ae` at 17:36 and the state did not change.

### Problem statement

The binding request succeeded and the target row has an `attribution_due`, but no consumer ever claimed it. After 25 minutes there was no owner, no failure, no report, and no retry; the target page only says “bound”, so users cannot tell from the list or detail whether attribution is running. The production host has neither `HE_ATTRIBUTION_AGENT` nor bubblewrap, so adding only the switch would let the batch claim and then fail, consuming the binding. The object actually has 22 pending Badcases, so this is not an empty-data case.

### Root-cause localization

1. **Confirm the binding and queue state**: the PUT at 17:13:08 returned 200; package, generation, due, and cutoff were all written; at 17:39 it was still `owner=NULL`, `failures=0`, `error=NULL`, `updated_at=17:13:08`, so the worker did not fail during execution — it never claimed the row.
2. **Confirm whether the consumer started**: the lifespan in `apps/api/app/main.py` calls `binding_worker.start()` only when `resolved_settings.attribution_agent` is non-empty; neither `/opt/harness/shared/.env` nor the `harness-api` process environment has `HE_ATTRIBUTION_AGENT`, and the release directory has no local `.env`; `config.py` defaults it to `None`, and `.env.example` says an empty value disables local attribution.
3. **Confirm whether any output exists**: under `attribute/<workspace>/` only `attribute_source` and `attribute_skill` exist; there is no `attribute_input` or `attribute_output`, and no batch directory for generation `01M83TWE...`; the journal has no log from that worker.
4. **Confirm the data is not empty**: 22 sessions contain skill events for `codespec-subagent-driven-development`, each with one `discovery` Badcase (22 cases, all before the cutoff); the associated data exists and no re-binding is needed after the fix.
5. **Confirm the runtime prerequisites**: the host has no bubblewrap package, `bwrap` is not on PATH, and `shutil.which("bwrap")` is `None` for the service account; `apps/api/app/third_party_api/ai_agent/claude_skill.py` raises `attribution requires bubblewrap on Linux` on Linux without bwrap. Adding only `HE_ATTRIBUTION_AGENT=provider` would let the batch claim and then fail; after three failures `attribution_due=NULL` and the binding is consumed.
6. **Confirm UI visibility**: the target page only has one hint inside the edit dialog; the list and detail have no persistent state. After the service was redeployed to `065a96ae` at 17:36, due/owner were unchanged, so this is not a one-off request failure.

### Conclusion

- Direct cause: the production runtime was not enabled (`HE_ATTRIBUTION_AGENT` missing), so `BindingWorker` never started and the binding stayed queued.
- Second blocker: the host lacks bubblewrap; even with only the switch added, the first batch would fail and consume its retries.
- Amplifier: the UI only hints inside the edit dialog and has no persistent state after binding; seeing “bound” makes users believe attribution has started.
- Not the root cause: binding persistence, generation/due creation, object matching, and the 22 Badcase records are all healthy; this is not a binding-API or data-plane defect.
- Fix direction: reuse the existing AI Agent configuration to supply the attribution switch (`HE_ATTRIBUTION_AGENT=provider`), add runtime/release preflights and visible state, and install bubblewrap in production so the existing generation is processed automatically.

## Goals

- Reuse the existing AI Agent configuration: add no second provider/model/API key; when `AI_AGENT_PROVIDER` is non-empty, Deploy injects `HE_ATTRIBUTION_AGENT=provider`, reusing the same CLI, shared settings, and `ANTHROPIC_API_KEY`.
- Make an unavailable runtime visible: the target configuration page and target overview keep showing the reason when `runtimeEnabled=false`, and bound rows show “attribution not running”.
- Fail fast when a prerequisite is missing: log a stable error code and skip the worker at startup without claiming or consuming the queued binding; fail the release preflight before switching `current`.
- Recover production: after bubblewrap is installed, the existing generation `01M83TWE...` automatically processes about 22 Badcases; the docs give enablement and verification steps.

## Design authority

- [Attribution Agent executor note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-17-attribution-agent-executor.md): local Skill execution uses a per-attempt filesystem sandbox (Linux bubblewrap), and `HE_ATTRIBUTION_AGENT` is the explicit switch.
- [07 §5.5.1 AI Agent Provider outbound adapter](../../../plans/fullstack-design/07-backend-implementation.md): the Provider capability surface and the Skill-support boundary.
- [07 §5.13 Attribution generation and cache](../../../plans/fullstack-design/07-backend-implementation.md): binding batches, generation, report writes, and retry semantics.
- [05 §4.1 Base endpoints: health check and authentication](../../../plans/fullstack-design/05-api-design.md): health checks are the release probe and errors must be diagnosable.
- [docs/deployment.md](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/deployment.md) and the [`HE_ATTRIBUTION_AGENT` example](https://github.com/Shadow-Azure/harness-evolution/blob/main/.env.example): deployment injection, the configuration switch, and the bubblewrap prerequisite.
- `.github/workflows/deploy.yml`: the existing AI Agent injection (`AI_AGENT_PROVIDER`, `HE_AI_AGENT_CLAUDE_BIN`, `HE_AI_AGENT_CLAUDE_SETTINGS`, `CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY`) and its unset-when-missing pattern; the attribution switch can reuse the same channel.
- `apps/api/app/main.py`, `apps/api/app/config.py`, `apps/api/app/service/evolution/local_attribution.py`, and `apps/api/app/third_party_api/ai_agent/claude_skill.py`: the worker gate, the `provider` selector, and the current bwrap check.

## Implementation

The root-cause fix has three layers: reuse the existing AI Agent configuration to supply the switch, add runtime/release preflights, and surface the state in the UI and docs.

- **Reuse the existing AI Agent configuration (recommended)**: `HE_ATTRIBUTION_AGENT=provider` already reuses the shared `AIAgentProvider`; Deploy injects `HE_ATTRIBUTION_AGENT=provider` when `AI_AGENT_PROVIDER` is non-empty and `--unset`s it when empty, adding no Secret, model, or API key. Teams that need an explicit override can add a Variable/Secret with the same name; do not hard-code it on in `Settings`. A production deployment that already has `AI_AGENT_PROVIDER=claude-code` then gets the attribution switch automatically while retaining an explicit way to disable it.
- **Startup preflight**: compute `attribution_ready = attribution_enabled and preflight_ok` in `main.py`; `preflight_ok` checks `shutil.which("bwrap")` on Linux and reuses the Skill-support check in `local_attribution.configured_skill_provider()`. Use `attribution_ready` for `runtime_enabled`, `default_package_id`, the `local_agent` preview, and `binding_worker.start()`. On failure, log a stable event (for example `attribution.preflight` with an `error_code`, without credentials or body content), do not start the worker, do not claim, and keep the queued binding.
- **Release preflight**: in `deploy/release.sh`, after reading `.env` and before migrating or switching `current`, exit with a clear message when `HE_ATTRIBUTION_AGENT` is non-empty and `command -v bwrap` fails; the old release keeps serving. Put the check in a testable helper or a reusable shell function instead of relying only on a manual check outside CI.
- **Frontend visibility**: add a page-level notice in `apps/web/src/pages/evolution/targets/Index.vue` when `runtimeEnabled === false`, saying “attribution runtime unavailable: the attribution Agent is off or bubblewrap is missing; saved bindings will not run and will start after a fix and restart”; add an “attribution not running” badge in `TargetTable.vue` for targets with a non-empty `attributionSkillName`. Reuse the notice/badge in `apps/web/src/pages/overview/components/TargetsOverview.vue` and update the old hint in `TargetFormDialog`. Reuse the existing `runtimeEnabled` from `/attribution-skill-packages`; add no API field or contract.
- **Docs**: add an “enable attribution” subsection to `docs/deployment.md` / `.en.md`: reuse the existing AI Agent configuration (`HE_ATTRIBUTION_AGENT=provider`, no new model/key), the bubblewrap prerequisite, steps (install bubblewrap, deploy or edit `.env`, restart, watch logs), and verification (target owner/due, `attribute_output/<generation>`, reports on the page). Add the reuse path and the bubblewrap prerequisite link to the `HE_ATTRIBUTION_AGENT` note in `.env.example`.
- **Tests**: API unit tests for “enabled + bwrap missing sets `attribution_ready=false`, does not start or claim”, “enabled + prerequisites present starts the worker”, and “disabled skips the preflight”; Deploy tests for injecting `HE_ATTRIBUTION_AGENT=provider` when `AI_AGENT_PROVIDER` is non-empty and unsetting it when empty; web unit tests for the notice/badge; a minimal executable test for the release check (if no shell fixture exists, extract a helper and unit-test it; do not claim an untested shell condition as verified).

## Implementation steps

1. Wire Deploy: add `HE_ATTRIBUTION_AGENT=provider` to the existing AI Agent injection step when `AI_AGENT_PROVIDER` is non-empty, and unset it when empty; confirm no new provider/model/key configuration.
2. Startup preflight and `attribution_ready` wiring with API unit tests.
3. Release preflight (helper/test) and confirmation that it fails before switching `current`.
4. Frontend notice and badge with unit tests.
5. Update the bilingual deployment docs, the `.env.example` note, and the Agent Note.
6. On the production host, install bubblewrap, deploy or restart, watch the existing generation being claimed and completed for about 22 cases, and run the gates and production acceptance.

## Dependencies and boundary

- Dependencies: none; the local attribution Agent, binding worker, existing AI Agent injection, and 22 pending Badcases already exist.
- Boundary: only the reused deployment switch, preflights, visibility, and docs change; code changes stay within the scope. Production enablement is an acceptance step; the API does not enable it automatically and the application process does not install system packages.
- Non-goals: do not change binding/generation/due semantics, the attribution engine, retry counts, or report format; do not add a second AI Agent provider/model/API key; do not add API fields or contracts; do not modify the AI Agent provider or sandbox implementation; do not write production credentials or Session content.

## Verification

```sh
pnpm test:api -- tests/test_attribution_preflight.py
pnpm test:gates
pnpm lint:api
pnpm typecheck:api
pnpm test
pnpm lint:web
pnpm typecheck:web
pnpm verify:docs
pnpm verify:flow
bash -n deploy/release.sh
```

- Unit tests prove: enabled but bwrap missing gives `attribution_ready=false`, does not start the worker, and leaves the target row at `owner=NULL/failures=0`; complete prerequisites start the worker; disabled produces no preflight error.
- Frontend tests prove: `runtimeEnabled=false` shows the notice and the badge on bound target rows; `runtimeEnabled=true` hides them.
- Deploy tests prove: with `AI_AGENT_PROVIDER=claude-code`, `.env` contains `HE_ATTRIBUTION_AGENT=provider` with no second model/key configuration; with an empty `AI_AGENT_PROVIDER`, the key is unset.
- The release check exits non-zero with a temporary `.env` and a PATH without bwrap, and does not switch `current`; documentation and flow gates are green and `bash -n` passes.
- Production verification: after deployment/restart `attribution_owner` becomes non-null within two seconds; `attribute_output/01M83TWE...` appears; the target page shows about 22 reports/analyses; no re-binding is needed.

## Acceptance

- Deploy reuses the existing AI Agent configuration: when `AI_AGENT_PROVIDER` is non-empty, `.env` automatically has `HE_ATTRIBUTION_AGENT=provider`, with no new Secret, provider, model, or API key; when `AI_AGENT_PROVIDER` is empty, attribution stays off.
- When the runtime is off or bubblewrap is missing, the target configuration page and target overview keep showing “attribution runtime unavailable, bindings will not run”, and bound rows have a visible badge; the edit-dialog hint is no longer the only signal.
- When enabled but bubblewrap is missing, the startup log has a stable error and the worker is skipped; the queued binding is not claimed and its failure count does not increase; the release preflight fails before switching `current`, and the previous release keeps serving.
- When the runtime and prerequisites are complete, the existing generation `01M83TWE...` is claimed automatically and completes about 22 Badcases; the target page shows reports; no re-binding is needed.
- Relevant unit tests, frontend tests, Deploy tests, documentation/flow gates, and `bash -n` pass; CI is green.

## Gates and CI

- `pnpm test:api`, `pnpm test:gates`, `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test`, `pnpm lint:web`, `pnpm typecheck:web`, `pnpm verify:docs`, `pnpm verify:flow`.
- If `deploy/release.sh` changes, run at least `bash -n` and the focused preflight test; if `.github/workflows/deploy.yml` changes, add a Deploy injection test and confirm that a missing/empty `AI_AGENT_PROVIDER` does not leave a stale switch.
- Commits and PR titles carry this issue number; do not write production credentials, Session content, or private data to the repository.

## Non-goals

- Do not add a second AI Agent provider/model/API key; reuse `AI_AGENT_PROVIDER` and the shared CLI/settings/key.
- Do not hard-code the `attribution_agent` default to `provider` in `Settings`; enablement is decided by Deploy injection or an explicit override.
- Do not install system packages from the API or deployment script; when bubblewrap is missing, fail with installation instructions only.
- Do not change binding persistence, generation, due, retry, or deletion semantics for queued bindings; do not change the attribution engine, report format, model, or Skill content.
- Do not add API/contract fields or change the health-check response shape; do not modify the existing AI Agent provider or sandbox implementation.
- Do not write production credentials, Session content, or private data.
