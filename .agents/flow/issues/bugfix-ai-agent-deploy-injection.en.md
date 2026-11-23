# Inject the AI Agent config trio into .env via GitHub Secrets (absent means unset)

English | [中文](bugfix-ai-agent-deploy-injection.md)

```yaml flow
kind: issue
id: bugfix-23
milestone: bugfix
depends:
  - bugfix-15
  - bugfix-17
  - bugfix-21
priority: P2
status: done
scope:
  - deploy/**
  - .github/workflows/deploy.yml
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - apps/api/tests/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 499
  url: https://github.com/Shadow-Azure/harness-evolution/issues/499
```

## Background

Three runtime keys of the real-model self-evolution loop take effect only when the deployment pipeline writes them into the production .env: `AI_AGENT_PROVIDER` (bugfix-15, selects fake / claude-code), `HE_AI_AGENT_CLAUDE_BIN` (bugfix-17, CLI path, default `~/.local/bin/claude`), and `HE_PATCH_SOURCE_MODE=agent-edit` (bugfix-21, patch source). The requirement: the three keys flow through GitHub Secrets, and **a key missing from Secrets must not exist in .env** — today inject-config.py's semantics are "secret absent → no key line emitted → the server-side old value survives", which lets a removed Secret keep taking effect (e.g. after switching away from agent-edit, a stale value still points at it). An unset path must be added.

## Goals

- The deploy workflow's (`.github/workflows/deploy.yml`) .env injection step gains the three keys: a present, non-empty Secret appends `KEY base64(value)` to `ENTRIES`; an absent or empty Secret appends the matching `--unset KEY` to `UNSET_ARGS` (following the existing conditional-unset pattern of HE_GIT_PROXY / HE_GIT_PUSH_TOKEN).
- The keys keep their names and meanings: `AI_AGENT_PROVIDER`, `HE_AI_AGENT_CLAUDE_BIN`, `HE_PATCH_SOURCE_MODE` (whose legal values gain `agent-edit` via bugfix-21).
- `deploy/env.production.example` gains the three examples with default-value comments (fallbacks when unset: `claude-code` / `~/.local/bin/claude` / `placeholder`).
- `docs/deployment.md` gains a section: the Secret names, semantics, defaults, and the "absent means unset" behavior.

## Design basis

- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md): the three config items' definitions and defaults.
- The existing patterns in `.github/workflows/deploy.yml`: conditional ENTRIES appending (the optional CLAUDE_CODE_BASE_URL precedent) and conditional UNSET_ARGS (the HE_GIT_PROXY precedent); `deploy/inject-config.py`'s atomic merge and `--unset` semantics.
- [docs/deployment.md](../../../docs/deployment.en.md) and [docs/claude-code.md](../../../docs/claude-code.en.md): the existing Secret → server-config documentation structure.

## Implementation

- Workflow injection step: three new Secret envs; present → ENTRIES, absent → UNSET_ARGS; values never leak (existing base64 + stdin channel).
- `env.production.example` and `docs/deployment.md` gain the three keys.
- Unit tests (matching the existing gates.spec / deploy test shape): assert inject merges the three keys when present, and removes them via --unset when absent; assert the workflow's ENTRIES/UNSET_ARGS assembly where testable.

## Steps

1. Workflow: three Secret envs plus conditional ENTRIES / UNSET_ARGS.
2. env.production.example and docs/deployment.md updates.
3. Unit tests and regression over existing deploy tests.
4. Gates: `pnpm lint:api`, `pnpm test:gates`, `pnpm verify:flow`.

## Dependencies and delivery boundary

- Dependencies: bugfix-15 (AI_AGENT_PROVIDER validation), bugfix-17 (CLAUDE_BIN consumption), bugfix-21 (the agent-edit enum).
- Delivery boundary: deployment wiring, examples, documents, and related tests only; no Settings changes and no change to inject-config.py's existing atomic-write semantics (--unset is already built in).

## Independent verification

```sh
pnpm test:gates
pnpm verify:flow
grep -c "AI_AGENT_PROVIDER\|HE_AI_AGENT_CLAUDE_BIN\|HE_PATCH_SOURCE_MODE" deploy/env.production.example
```

- Gates green; grep prints ≥3 (all three key examples present).

## Acceptance criteria

- All three Secrets set: the server .env carries the configured values and they take effect after a service restart (fake / claude-code selectable).
- All three Secrets absent: the keys do not exist in .env (--unset removes stale values) and the service runs on defaults (claude-code / default path / placeholder).
- Partially set: unset keys are removed, present keys are written, no cross-effect.
- CI green.

## Gates and CI

- api-static / docs-flow (test:gates, verify:docs) / the deploy-related lane.
- Commit and PR titles carry `(#N)`.

## Non-goals

- No GitHub Variables or workflow-input variants for the three keys (Secrets stay the single channel).
- No changes to inject-config.py's transport or atomic-write protocol.
- No semantic changes to the CLAUDE_CODE_* install-type Secrets (M15 scope).
- No additional HE_AI_AGENT_* keys (the over-engineering trim is settled, see #497).
