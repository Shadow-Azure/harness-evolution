# Select the Linux attribution runtime through the service environment

English | [中文](bugfix-attribution-runtime-mode.md)

```yaml flow
kind: issue
id: bugfix-55
milestone: bugfix
depends:
  - bugfix-32
priority: P2
status: ready
scope:
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/pyproject.toml
  - apps/api/tests/**
  - apps/web/src/pages/evolution/targets/components/AttributionRuntimeNotice.vue
  - .env.example
  - attribute/README*
  - docs/deployment*
  - plans/deploy-aliyun-playbook.md
  - plans/fullstack-design/02-features.md
  - .agents/notes/implemented/**
  - .agents/flow/issues/bugfix-attribution-runtime-mode*
adr:
  - ../../notes/implemented/architecture/2026-11-17-attribution-agent-executor.md
github:
  number: 595
  url: https://github.com/Shadow-Azure/harness-evolution/issues/595
```

## Background

An existing Linux host may lack bubblewrap. The default Claude provider reports the missing package before release and before claiming an attribution batch. Administrators need a runtime choice that fits the existing host setup. See #544 for the preflight checks.

## Goals

Select a common execution mode for binding attribution and wizard recomputation through the service `.env`. Keep bubblewrap as the default.

## Design authority

Both entry points share the provider, model, frozen inputs and report contract. [Object binding attribution](../../../plans/fullstack-design/02-features.md#对象绑定归因)

## Implementation

The shared Claude provider reads `HE_ATTRIBUTION_BWRAP_ENABLED`. On Linux it runs the frozen Skill inside bubblewrap by default. When explicitly set to `false`, Claude reads the current Badcase and Skill resources with `read_evidence` and calls the platform report script through `write_probe_report`.

## Implementation steps

1. Pass the service setting to the provider preflight and the per-case Skill runner.
2. Restrict the files exposed by the evidence tool, let the platform fix the report identity and destination, and verify the write receipt.
3. Record the mode at startup and in each attribution log, then verify the results from both entry points.

## Dependencies and boundary

The existing release script exports the service `.env` and runs Python preflight before database migration. Host setup and package installation follow the deployment process on `main`.

## Verification

```sh
pnpm test:api:serial -- tests/test_attribution_preflight.py tests/attribution/test_case_tools.py
pnpm test:api:serial -- tests/m5-05-launch-wizard/test_launch_api.py::test_startup_claims_existing_binding_with_shared_provider tests/m5-05-launch-wizard/test_launch_api.py::test_local_attribution_from_wizard_to_cluster
```

The tests use temporary SQLite, synthetic Badcases and an offline Claude CLI. With the package missing, the default mode keeps the binding queued. An explicit opt-out resumes the same generation and persists its reports.

## Acceptance criteria

- With the setting omitted or explicitly enabled, a missing package and a failed namespace probe produce their respective errors.
- With the setting explicitly disabled, binding attribution and wizard recomputation can read the case evidence and store the report from the platform script. The execution log records `case-tools`.
- The PR and `main` have identical `deploy/` trees.

## Gates and CI

API regression tests cover release preflight, bindings, the wizard and clustering. The Ubuntu `deploy-contract` job checks the runtime with the package absent and after installation.

## Non-goals

Host package installation, report format, cache selection and object binding rules follow their existing contracts.
