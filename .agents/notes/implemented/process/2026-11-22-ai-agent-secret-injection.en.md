# Agent Note: Injecting the AI Agent config trio from GitHub Secrets

Status: implemented

English | [中文](2026-11-22-ai-agent-secret-injection.md)

## Problem

Model review and patch generation in the evolution loop depend on three runtime keys — `AI_AGENT_PROVIDER`, `HE_AI_AGENT_CLAUDE_BIN`, and `HE_PATCH_SOURCE_MODE` — and production values must reach the server's `/opt/harness/shared/.env` through the deploy pipeline. `inject-config.py`'s existing semantics are "keys absent from stdin keep the server's old value", so deleting a Secret leaves its old value in effect; switching away from `agent-edit` to `placeholder` would still leave the stale `agent-edit` behind. Treating Secrets as the single source of configuration therefore requires absence to be an explicit state.

## Decision

The three Secrets share their names with the keys: when a Secret is present and non-empty, the deploy step appends `KEY base64(value)` to `ENTRIES` and hands it to `inject-config.py` over the existing base64 + stdin channel; when it is absent or empty, the step appends `--unset KEY` to `UNSET_ARGS`. Writing and removing the three keys thus ride the same mechanism as the conditional proxy/token unset, and logs report the written count plus the remaining removals only, never values. `HE_PATCH_SOURCE_MODE=agent-edit` is not enabled here: Settings currently accept only `placeholder` / `minimal-config`, so writing `agent-edit` fails startup validation until #488 (bugfix-21) lands.

## Alternatives considered

GitHub Variables instead: the three keys are not sensitive, but that would add a second configuration channel, and Variables differ in visibility and precedence across fork PRs and environment overrides, breaking the established "Secrets are the single source" boundary. `workflow_dispatch` inputs: only manual runs have inputs, automatic main-push deploys do not, so behavior would drift by trigger. Making `inject-config.py` drop keys missing from stdin: that changes the script's semantics for every caller and cannot distinguish "nothing was meant to be injected this run" from "the Secret was deleted"; an explicit `--unset` keeps the intent in the workflow layer. Hard-coding the three keys in the env template: production values do not live in the repository, and the template only documents examples and defaults.

## Consequences

Every deploy explicitly sets or removes the three keys, keeping the server `.env` isomorphic to the Secrets; after a Secret is deleted, a restart falls back to the Settings defaults (`claude-code` / `~/.local/bin/claude` / `placeholder`). The workflow rejects newline/carriage-return values for the three keys before assembly and aborts the deploy: a skipped value is not a deletion, so no old value survives a decode skip; other keys still warn and skip. The injection channel does not validate enums, so illegal values still fail the service's startup validation; the fallback defaults are not guaranteed to work under `harness` — the CLI's settings and credentials must be readable by that user, and stable paths plus shared settings are bugfix-17/M15 work. `agent-edit` availability depends on #488. New keys from the same family should follow the "present writes / missing unsets" pattern so stale keys cannot linger.
