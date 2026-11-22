# Claude Code subclass: headless invocation, process management, and usage collection

English | [中文](bugfix-claude-code-provider.md)

```yaml flow
kind: issue
id: bugfix-17
milestone: bugfix
depends:
  - bugfix-15
  - bugfix-16
priority: P2
status: in-progress
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/config.py
  - apps/api/tests/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 492
  url: https://github.com/Shadow-Azure/harness-evolution/issues/492
```

## Background

With the skeleton (bugfix-15) and the submission channel (bugfix-16) in place, the first real subclass is needed: reuse the production-deployed `claude` CLI (M15) to serve `analyze` and `edit_workspace`. This issue covers the subclass only — business wiring arrives in bugfix-19/21.

## Goals

- Add `third_party_api/ai_agent/claude_code.py`: `ClaudeCodeProvider`, registered as `claude-code`, implementing the three abstract methods.
- **analyze path**: `claude --bare -p <prompt> --output-format json --permission-mode dontAsk --allowed-tools "Write(./result.json5)" --settings <deployed settings>`; conclusions collected through the submission channel; on validation failure retry once via `--resume <session_id>` with feedback.
- **edit_workspace path**: read-only tools plus `Write(./.harness-evolution/edits.json5)` (this issue lands EditPlan submission and collection only; the deterministic applier is bugfix-20).
- **Process management**: `create_subprocess_exec` + `start_new_session=True` + `asyncio.wait_for`; SIGINT first on timeout/cancel, then `killpg(SIGKILL)`; exit code 143 is classified "cancelled", not failure.
- **Usage collection**: map result `total_cost_usd` / `model_usage` / `session_id` into `AgentUsage`.
- No `--json-schema` fast path: the submission channel (self-built literal collection) is the default and only path, avoiding two pathways and an extra config switch.

## Design basis

- [07 §5.5.1](../../../plans/fullstack-design/07-backend-implementation.md): subclass process-management posture (reusing the git workspace pattern), zero credential awareness, the fake-first boundary.
- [07 §5.5.3](../../../plans/fullstack-design/07-backend-implementation.md): headless invocation spec, the `--bare`/`--settings` decisions, and SIGINT signal semantics.

## Implementation

- Injectable process seam (mocked-subprocess unit matrix: timeout kill, non-zero exit, 143 cancel, stream-json final result line).
- Capability detection via `system/init.capabilities`, never version-string comparison.
- analyze adds `--no-session-persistence`; the edit path keeps sessions (`--resume` for iteration).
- An e2e smoke behind an env switch (serial lane; skippable where no CLI exists).

## Steps

1. Implement claude_code.py and register it.
2. Mocked-subprocess unit matrix.
3. E2E smoke (optional switch).
4. Gates: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm verify:flow`.

## Dependencies and delivery boundary

- Dependencies: bugfix-15 (skeleton), bugfix-16 (submission collection).
- Delivery boundary: subclass and tests only; no clustering/patch business wiring; the deterministic edit applier is bugfix-20.

## Independent verification

```sh
pnpm test:api -- tests/test_ai_agent_claude_code.py
```

- The mock matrix is green: normal, timeout, non-zero exit, 143 cancel, resume retry.

## Acceptance criteria

- With `AI_AGENT_PROVIDER=claude-code` the factory yields the real subclass; analyze output passes the caller's schema.
- Timeout and cancel paths kill the process group with correct classification; usage/session_id fields are complete.
- The submission channel is the default and only path; no native fast-path switch.
- CI green; unit tests stay offline.

## Gates and CI

- api-static / unit-tests-api / docs-flow / e2e (smoke switch).
- Commit and PR titles carry `(#N)`.

## Non-goals

- No clustering/scoring/patch business wiring (bugfix-19/21).
- No edits.py applier (bugfix-20).
- No OpenCode/model subclasses.
