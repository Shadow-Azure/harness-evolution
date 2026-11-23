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
  - apps/api/app/service/evolution/attribution_skills.py
  - apps/api/app/service/evolution/local_attribution.py
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/tests/**
  - apps/web/src/pages/evolution/targets/**
  - apps/web/src/pages/evolution/components/LaunchWizard*
  - apps/web/src/pages/overview/components/TargetsOverview.vue
  - apps/web/src/pages/overview/components/TargetSideList.vue
  - apps/web/src/pages/overview/Index.test.ts
  - tests/e2e/m5-target-config.test.mjs
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
- The fix uses the shared provider from #542. Binding attribution, wizard recomputation and release checks use the same provider selection. On Linux, Claude verifies that bubblewrap can start an isolated process before claiming work.

## Goals

A saved binding resumes once its dependencies recover. Target configuration and the target overview show a persistent paused state. Operators can distinguish an unsupported provider, missing bubblewrap and an unusable namespace in startup and deployment logs.

## Design authority

- [07 §5.5.1 AI Agent outbound adapter](../../../plans/fullstack-design/07-backend-implementation.md) defines the shared provider, model settings and Skill capability.
- [07 §5.13 attribution and caching](../../../plans/fullstack-design/07-backend-implementation.md) defines generations, leases and report persistence. [Target-bound attribution](../../../plans/fullstack-design/02-features.md#对象绑定归因) describes the background and wizard behavior.

## Implementation

- The API and release command resolve `AI_AGENT_PROVIDER` through the shared factory, defaulting to `claude-code`. The provider supplies the model, CLI and credentials. Legacy attribution switches are ignored.
- The API emits `attribution.preflight` with `ATTRIBUTION_BWRAP_MISSING` for an absent binary, `ATTRIBUTION_BWRAP_UNUSABLE` for a failed namespace probe and `ATTRIBUTION_PROVIDER_UNSUPPORTED` for a provider without Skill capability. Readiness controls `runtimeEnabled`, `canRecompute` and the binding consumer. Saved bindings, historical reports and cached runs remain available.
- Before migrating or switching `current`, the release script checks the same provider through the candidate API. A failed Linux Claude sandbox probe aborts the release and restores the environment backup. An explicit cache-only `fake` deployment can proceed. The API repeats the check under the service account.
- Both target pages show a persistent notice while the runtime is unavailable and mark bound rows “归因未运行”. The edit dialog and wizard use the same status.

## Implementation steps

1. Wire provider preflight into the API, binding consumer, wizard and release.
2. Update both target views, deployment documentation and configuration template. Cover paused, recovered and ready states.
3. Verify recovery of the original batch and retention of the previous release in isolation. Operators validate the original generation and reports after production deployment.

## Dependencies and boundary

Use the existing bindings, snapshots, public AI Agent configuration and package-list contract. Administrators install bubblewrap and provide usable namespaces for the service account. Production acceptance is separate from synthetic verification.

## Verification

```sh
pnpm test:api -- --serial tests/test_attribution_preflight.py tests/m5-05-launch-wizard/test_launch_api.py::test_startup_claims_existing_binding_with_shared_provider
pnpm test:web
pnpm test:e2e --pattern 'm5 target configuration'
bash -n deploy/release.sh
```

Create 22 synthetic Sessions in one temporary SQLite database, each with a discovery Badcase, and bind the default package. With a simulated missing Linux bwrap, owner stays empty, due stays set and failures stay at zero. Restart with a working test Skill provider and verify the same generation, 22 reports, bound Skill and per-case logs. Run the release script with a missing, failing or working binary and a cache-only provider.

## Acceptance

- Failed prerequisites cause zero claims and retries. Both target views show the paused state. Existing bindings persist and past reports can be reused.
- A missing or unusable sandbox interrupts deployment before migration and the current release continues serving.
- Once production recovers, generation `01M83TWE7ZSTC6Z5MNF0P0KQDM` automatically processes the original 22 Badcases. Verify the database reports, target page and output files by generation and Skill.

## Gates and CI

Run API and Web tests, lint and type checks, browser integration, `pnpm verify:docs`, `pnpm verify:flow`, `pnpm test:gates` and release preflight tests.

## Non-goals

The existing contracts govern leases, retries, report format and Skill isolation. Operators own host package installation and production data verification.
