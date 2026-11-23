# AI Agent Provider skeleton: contracts, factory, fake, and settings wiring

English | [中文](bugfix-ai-agent-provider-skeleton.md)

```yaml flow
kind: issue
id: bugfix-15
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - .agents/**
  - plans/**
adr:
  - ../../notes/implemented/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 490
  url: https://github.com/Shadow-Azure/harness-evolution/issues/490
```

## Background

The real-model self-evolution design has landed (#487): outbound model calls converge on the parent-contract + subclass + factory seam in `third_party_api/ai_agent`. This issue is the first step of the implementation route — skeleton only, with no real backend and no business wiring.

## Goals

- Add the `apps/api/app/third_party_api/ai_agent/` package: `contracts.py` (AnalysisRequest/AnalysisResult, EditRequest/EditResult, AgentUsage, ProviderHealth, AgentProviderError), `base.py` (the `AIAgentProvider` ABC), `factory.py` (registry + `build_agent_provider(settings)`), `fake.py` (a deterministic `FakeAIAgentProvider`).
- `Settings` adds exactly two entries: `ai_agent_provider` (`AliasChoices("AI_AGENT_PROVIDER","HE_AI_AGENT_PROVIDER")`, default `claude-code`, validator restricted to registry values) and `ai_agent_claude_bin` (default `~/.local/bin/claude`, the M15 deployment path — zero-config). **No other sub-config items** — timeouts (analyze 300s / edit 1800s) and the permission mode (`dontAsk`) are code constants, avoiding over-engineering.
- `main.py` wiring: build the provider singleton onto `app.state`; lifespan runs `health_check` and records an event.
- Unit tests: factory selection, unknown-value startup failure, deterministic fake analyze/edit_workspace, normalized error fields.

## Design basis

- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md): the three parent capability faces (analyze/edit_workspace/health_check), normalized result fields, factory and `AI_AGENT_PROVIDER` selection semantics.
- [04 §5.1](../../../plans/fullstack-design/04-backend-architecture.md): `ai_agent` is the single model-egress seam, not a revival of the unified Provider.
- Repo precedents: `PatchSource` (protocol + factory + env fallback), `GitPushProvider` (ABC + registry factory), `FakeEvalGateway` (fake first).

## Implementation

- `contracts.py` uses frozen dataclasses with docstrings matching the export-comment convention; `AgentProviderError(message, *, retryable, provider_id, detail)`.
- `factory.py` keeps a module-level registry; this issue registers `fake` only — the `claude-code` key is reserved for bugfix-17 (either reject unregistered keys via Settings, or register an explicit placeholder raising `NotImplementedError`, whichever tests easier).
- `fake.py`: analyze returns fixed structures per task key that pass the caller's schema; edit_workspace returns a fixed EditResult.
- Wiring attaches no service consumer — business integration arrives in bugfix-18/19/21.

## Steps

1. Create the package and four modules; Settings fields and validator.
2. main.py wiring + lifespan health event.
3. Unit tests (fake throughout, no network).
4. Gates: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm verify:flow`.

## Dependencies and delivery boundary

- Dependencies: none (the root of the whole chain).
- Delivery boundary: only the `ai_agent` package, Settings, wiring, and tests; no service/evolution business code; no real subclass.

## Independent verification

```sh
pnpm test:api -- tests/test_ai_agent_factory.py
AI_AGENT_PROVIDER=unknown python -c "from app.config import Settings; Settings(_env_file=None)"
```

- Tests green; the second command raises a validation error containing `unknown AI agent provider` (fail at startup).

## Acceptance criteria

- Four modules present; factory selects by env; unknown-value startup failure pinned by a test.
- `FakeAIAgentProvider` is usable by the business layer without adaptation (later issues test entirely through it).
- The provider is reachable on `app.state`; lifespan records the health event.
- CI green; coverage keeps the existing floor.

## Gates and CI

- api-static / unit-tests-api / docs-flow (test:gates, verify:docs).
- Commit and PR titles carry `(#N)`; scope covers `ai_agent/**`, `config.py`, `main.py`, tests, `.agents/**`.

## Non-goals

- No real Claude Code invocation (bugfix-17) and no submission channel (bugfix-16).
- No business wiring (bugfix-18/19/21).
- No OpenCode/model subclasses.
