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

Read-only checks confirmed:

- Neither `/opt/harness/shared/.env` nor the `harness-api` process environment has `HE_ATTRIBUTION_AGENT`; the release directory has no local `.env`. The lifespan in `apps/api/app/main.py` calls `binding_worker.start()` only when `resolved_settings.attribution_agent` is non-empty; `config.py` defaults it to `None`; `.env.example` says an empty value disables local attribution.
- Under `attribute/<workspace>/` only `attribute_source` and `attribute_skill` exist; there is no `attribute_input` or `attribute_output`, and no batch directory for generation `01M83TWE...`; the journal has no log from that worker.
- The binding dialog says “this deployment has not enabled the attribution Agent; the Skill binding is saved and background attribution starts after enabling”, but the target list/detail has no persistent state; seeing “bound” makes users believe attribution has started.
- The server has no bubblewrap: the package is absent, `bwrap` is not on PATH, and `shutil.which("bwrap")` is `None` for the service account. `apps/api/app/third_party_api/ai_agent/claude_skill.py` raises `attribution requires bubblewrap on Linux` on Linux without bwrap. Adding only `HE_ATTRIBUTION_AGENT=provider` would let the batch claim and then fail; after three failures `attribution_due=NULL` and the binding is consumed.
- The object appears in skill events of 22 sessions, each with one `discovery` Badcase (22 cases, all before the cutoff), so there is data to attribute; after the fix the existing due timestamp is claimed automatically and no re-binding is needed.

## Goals

- Make an unavailable runtime visible: the target configuration page and target overview keep showing the reason when `runtimeEnabled=false`, and targets with a bound Skill show “attribution not running” in the table instead of only a hint inside the edit dialog.
- Fail fast when a prerequisite is missing: log a stable error code for missing bubblewrap or a Provider without Skill support at startup, and skip `BindingWorker`; do not claim or consume the queued binding, and do not report the runtime as available.
- Make the release preflight fail before switching `current` and keep the previous release serving; after the production fix, the existing generation `01M83TWE...` automatically processes about 22 Badcases and the target page shows reports.
- Make the documentation executable: the deployment guide gives the prerequisites, steps, and verification commands for enabling attribution, and distinguishes “bound” from “running”.

## Design authority

- [Attribution Agent executor note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-17-attribution-agent-executor.md): local Skill execution uses a per-attempt filesystem sandbox (Linux bubblewrap), and `HE_ATTRIBUTION_AGENT` is the explicit switch.
- [07 §5.5.1 AI Agent Provider outbound adapter](../../../plans/fullstack-design/07-backend-implementation.md): the Provider capability surface and the Skill-support boundary.
- [07 §5.13 Attribution generation and cache](../../../plans/fullstack-design/07-backend-implementation.md): binding batches, generation, report writes, and retry semantics.
- [05 §4.1 Base endpoints: health check and authentication](../../../plans/fullstack-design/05-api-design.md): health checks are the release probe and errors must be diagnosable.
- [docs/deployment.md](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/deployment.md) and the [`HE_ATTRIBUTION_AGENT` example](https://github.com/Shadow-Azure/harness-evolution/blob/main/.env.example): deployment injection, the configuration switch, and the bubblewrap prerequisite.
- `apps/api/app/main.py`, `apps/api/app/config.py`, and `apps/api/app/third_party_api/ai_agent/claude_skill.py`: the worker gate, configuration default, and current hard bwrap check.

## Implementation

- **Frontend visibility**: add a page-level notice in `apps/web/src/pages/evolution/targets/Index.vue` when `runtimeEnabled === false`, saying “attribution runtime unavailable: the attribution Agent is off or bubblewrap is missing; saved bindings will not run and will start after a fix and restart”; add an “attribution not running” badge in `TargetTable.vue` for targets with a non-empty `attributionSkillName`. Reuse the notice/badge in `apps/web/src/pages/overview/components/TargetsOverview.vue` and update the old hint in `TargetFormDialog`. Reuse the existing `runtimeEnabled` from `/attribution-skill-packages`; add no API field or contract.
- **Startup preflight**: compute `attribution_ready = attribution_enabled and preflight_ok` when constructing the runtime in `main.py`; `preflight_ok` checks `shutil.which("bwrap")` on Linux and reuses the Skill-support check in `local_attribution.configured_skill_provider()`. Use `attribution_ready` for `runtime_enabled`, `default_package_id`, the `local_agent` preview, and `binding_worker.start()`. On failure, log a stable event (for example `attribution.preflight` with an `error_code`, without credentials or body content), do not start the worker, do not claim, and keep the queued binding.
- **Release preflight**: in `deploy/release.sh`, after reading `.env` and before migrating or switching `current`, exit with a clear message when `HE_ATTRIBUTION_AGENT` is non-empty and `command -v bwrap` fails; the old release keeps serving. Put the check in a testable helper or a reusable shell function instead of relying only on a manual check outside CI.
- **Docs**: add an “enable attribution” subsection to `docs/deployment.md` / `.en.md`: prerequisites (bubblewrap, AI Agent Provider/CLI/API Key, `HE_ATTRIBUTION_AGENT=provider`), steps (install bubblewrap, edit `.env`, restart, watch logs), and verification (target owner/due, `attribute_output/<generation>`, reports on the page). Add the bubblewrap prerequisite link to the `HE_ATTRIBUTION_AGENT` note in `.env.example`.
- **Tests**: API unit tests for “enabled + bwrap missing sets `attribution_ready=false`, does not start or claim”, “enabled + prerequisites present starts the worker”, and “disabled skips the preflight”; web unit tests for the notice/badge; a minimal executable test for the release check (if no shell fixture exists, extract a helper and unit-test it; do not claim an untested shell condition as verified).

## Implementation steps

1. Frontend notice and badge with unit tests.
2. Startup preflight and `attribution_ready` wiring with API unit tests.
3. Release preflight (helper/test) and confirmation that it fails before switching `current`.
4. Update the bilingual deployment docs and `.env.example` note, and add the Agent Note.
5. On the production host, install bubblewrap, set `HE_ATTRIBUTION_AGENT=provider`, and restart; watch the existing generation being claimed and completed for about 22 cases.
6. Run the gates and production acceptance.

## Dependencies and boundary

- Dependencies: none; the local attribution Agent, binding worker, and 22 pending Badcases already exist.
- Boundary: only preflight, visibility, deployment checks, and docs change; code changes stay within the scope. Production enablement is an acceptance step; the API does not enable it automatically and the application process does not install system packages.
- Non-goals: do not change binding/generation/due semantics, the attribution engine, retry counts, or report format; do not add API fields or contracts; do not change the default switch to on; do not modify the AI Agent provider or sandbox implementation; do not write production credentials or Session content.

## Verification

```sh
pnpm test:api -- tests/test_attribution_preflight.py
pnpm lint:api
pnpm typecheck:api
pnpm test
pnpm lint:web
pnpm typecheck:web
pnpm verify:docs
pnpm verify:flow
pnpm test:gates
bash -n deploy/release.sh
```

- Unit tests prove: enabled but bwrap missing gives `attribution_ready=false`, does not start the worker, and leaves the target row at `owner=NULL/failures=0`; complete prerequisites start the worker; disabled produces no preflight error.
- Frontend tests prove: `runtimeEnabled=false` shows the notice and the badge on bound target rows; `runtimeEnabled=true` hides them.
- The release check exits non-zero with a temporary `.env` and a PATH without bwrap, and does not switch `current`.
- Documentation and flow gates are green; `bash -n` passes.
- Production verification: after restart `attribution_owner` becomes non-null within two seconds; `attribute_output/01M83TWE...` appears; the target page shows about 22 reports/analyses; no re-binding is needed.

## Acceptance

- When the runtime is off or bubblewrap is missing, the target configuration page and target overview keep showing “attribution runtime unavailable, bindings will not run”, and bound rows have a visible badge; the edit-dialog hint is no longer the only signal.
- When enabled but bubblewrap is missing, the startup log has a stable error and the worker is skipped; the queued binding is not claimed and its failure count does not increase; the release preflight fails before switching `current`, and the previous release keeps serving.
- When the runtime and prerequisites are complete, the existing generation `01M83TWE...` is claimed automatically and completes about 22 Badcases; the target page shows reports; no re-binding is needed.
- The deployment docs contain executable enablement and verification steps; the `.env.example` note matches the implementation.
- Relevant unit tests, frontend tests, documentation/flow gates, and `bash -n` pass; CI is green.

## Gates and CI

- `pnpm test:api`, `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test`, `pnpm lint:web`, `pnpm typecheck:web`, `pnpm verify:docs`, `pnpm verify:flow`, `pnpm test:gates`.
- If `deploy/release.sh` changes, run at least `bash -n` and the focused preflight test; when a reusable helper is introduced, add its unit test.
- Commits and PR titles carry this issue number; do not write production credentials, Session content, or private data to the repository.

## Non-goals

- Do not enable attribution automatically and do not change the `HE_ATTRIBUTION_AGENT` default to `provider`.
- Do not change binding persistence, generation, due, retry, or deletion semantics for queued bindings.
- Do not change the attribution engine, report format, model, or Skill content.
- Do not install system packages from the API or deployment script; when bubblewrap is missing, fail with installation instructions only.
- Do not add API/contract fields or change the health-check response shape.
- Do not modify the existing AI Agent provider or sandbox implementation; only reuse its capability checks.
