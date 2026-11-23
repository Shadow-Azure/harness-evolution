# AI-call observability events and resident documentation wrap-up

English | [中文](bugfix-ai-agent-observability-docs.md)

```yaml flow
kind: issue
id: bugfix-22
milestone: bugfix
depends:
  - bugfix-19
  - bugfix-21
priority: P2
status: done
scope:
  - apps/api/**
  - docs/**
  - .agents/**
  - plans/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 489
  url: https://github.com/Shadow-Azure/harness-evolution/issues/489
```

## Background

After the implementation chain (bugfix-15→21) lands, this issue wraps up: complete `ai_agent_call` observability into operable metrics, refresh the resident documents (architecture/development/new ai-agent page), and keep the design Note in sync now that it lives under `implemented/`.

## Goals

- **Observability**: `ai_agent_call` events uniformly record task, provider, model, tokens, cost, latency, and outcome (including `degraded` and feedback-retry counts); the submission-file parse-failure rate is derivable from the event stream.
- **Documents**: add an ai-agent outbound-layer page under `docs/` (bilingual pair, word budget registered); update the "not yet available" list in `docs/architecture.md` to match what actually shipped (real patches landed; real evaluation stays described per the eval gateway's current state); extend `docs/development.md` with configuration notes — only `AI_AGENT_PROVIDER`, `HE_AI_AGENT_CLAUDE_BIN` (with default), and the `agent-edit` enum value of `HE_PATCH_SOURCE_MODE`.
- **Note**: `implemented/feature/2026-11-22-evolution-real-ai-design.md` stays in sync with landed facts (the triplet moved from `proposed/`).
- No AGENTS.md command-list additions (no new script commands).

## Design basis

- [07 §5.5.1–§5.5.3](../../../plans/fullstack-design/07-backend-implementation.md): observability fields and layer 5 of the six-layer defense.
- [docs/AGENTS.md](../../../docs/AGENTS.md): resident-document layering, bilingual pairing, and word-budget rules.
- [.agents/notes/README.md](../../notes/README.en.md): the Note lifecycle rule of staying in sync with reality.

## Implementation

- Verify event-field coverage and fill gaps; optionally one stats helper or query example.
- `HE_PATCH_SOURCE_MODE=agent-edit` passes configuration validation (otherwise the documented enum value cannot start).
- The three document changes + `pnpm record:i18n` + budget registration.
- Note status migration with fact sync.

## Steps

1. Audit event-field coverage; fill gaps.
2. Three document updates + budget + i18n.
3. Note migration.
4. Gates: `pnpm lint:docs`, `pnpm verify:docs`, `pnpm verify:flow`, `pnpm test:api`.

## Dependencies and delivery boundary

- Dependencies: bugfix-19 (clustering integration) and bugfix-21 (patch loop) — the observability and documents describe their final shape.
- Delivery boundary: observability events and documents/Note; no business-rule change, only minimal observability wiring and configuration validation.

## Independent verification

```sh
pnpm lint:docs && pnpm verify:docs
```

- Bilingual pairing, budget registration, and dead-link checks are green; event fields have test assertions.

## Acceptance criteria

- Every AI call is visible in run events with complete fields; degradation and retries are traceable.
- The new document page is bilingual with a registered budget; the architecture "not yet available" wording matches reality.
- The Note's status and facts are in sync.
- CI green.

## Gates and CI

- docs-flow (doc-sync) / api-static / unit-tests-api.
- Commit and PR titles carry `(#N)`.

## Non-goals

- No frontend observability dashboard.
- No new monitoring/alerting integrations.
- No Provider interface changes.
