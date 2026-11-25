# Portable AI agent backends: neutral skill layout, explicit capabilities, and a generic config entry

English | [中文](bugfix-ai-agent-portable-backend.md)

```yaml flow
kind: issue
id: bugfix-57
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/service/evolution/local_attribution.py
  - apps/api/app/service/evolution/patch_source.py
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/tests/**
  - docs/**
  - plans/**
  - .agents/**
  - attribute/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 604
  url: https://github.com/Shadow-Azure/harness-evolution/issues/604
```

## Background

### Problem statement

The outbound layer `third_party_api/ai_agent` claims in both docs and design that "switching AI agents means one subclass plus one registry entry" (`docs/ai-agent.en.md` layering section, 07 §5.5.1). A per-operation audit of `origin/main @ 2952c5f4` on 2026-11-25 shows the claim only holds when the backend runs analyze / edit_workspace / health_check. If Skill / attribution must follow the provider switch (the requester's explicit requirement), three vendor assumptions leak outside the subclass:

- **Skill layout and invocation syntax live in the service layer**: `service/evolution/local_attribution.py` `_stage_attempt` stages the frozen skill into `work/.claude/skills/<name>` plus a `.cac/skills` alias, and the execution prompt hardcodes the slash command `/{name} input_badcase.json，请分析并生成归因报告`. The slash command only resolves because the files are staged in the shape Claude recognizes; a CLI agent that does not understand `.claude/skills` and has no slash mechanism cannot receive the skill even with a correct `run_skill` implementation.
- **The config namespace is Claude-bound**: `app/config.py` only has the named fields `ai_agent_claude_bin` / `ai_agent_claude_settings` (a blank bin fails startup); a new backend has no typed entry for its binary and settings paths, so it must read raw env or modify `Settings`.
- **Capabilities are implicit and auth is outside the contract**: `base.py` derives `supports_skills` from "did the subclass override `run_skill`", so a subclass that forgets it silently degrades attribution to cache-only (one startup warning); `ProviderHealth` carries only `healthy` plus free-form `detail`, and Claude reports `healthy=True` without credentials — auth state lives only in startup logs, and `/api/health` excludes provider state.

Two minor contract debts are handled in passing: the edit submission filename exists twice (subclass constant `claude_code.EDIT_PLAN_FILENAME` vs the literal in `patch_source._edit_prompt`), and `base.py` exports the Claude-specific constant `PERMISSION_MODE`.

### Analysis (2026-11-25 encapsulation audit)

The audit split "what an agent integration must do" into six layers (contract / call surface / transport protocol / runtime config / lifecycle observability / delivery) and judged each. Verdict: the model-egress layer is well encapsulated — argv, process-group lifecycle, output parsing, usage normalization, permission rules, and error taxonomy all live on the vendor side (`claude_code.py` 1,280 lines + `claude_skill.py` 296 lines), the parent defines only three abstract methods, and the business layer has no backend branching (only the `fake` failure-policy derivation in `config.py` and the replay alias in `local_attribution.py`). But runtime config, auth state, skill layout, and delivery are not inside the subclass: "one subclass" holds for scenario A (analyze/edit/health only) and fails for scenario B (Skill/attribution must follow the provider) until the service layer changes. The full audit worksheet lives on branch `analysis/ai-agent-provider-audit` at `plans/ai-agent-provider-encapsulation-audit.html` (not committed; its conclusions are absorbed here).

Fact check on replay validation: `freeze()` writes `agent` (the then-current `provider_id`) and `modelIdentity` (derived from the then-current environment) into the manifest and pins the hash into the run/target; every subsequent attribution case execution — including post-restart `jobs.recover()` catch-up, failed-case retries, and attribution eval — resolves the provider from the frozen manifest and re-compares the identity (`local_attribution.py:555-557`). Old-snapshot replay is therefore load-bearing: the `{"claude", "...ClaudeBackend"} → "claude-code"` alias mapping must be kept, and a new backend's `skill_model_identity` must follow the existing shape contract (`dict[str, str]` with `selector`/`model`/`endpointHash` or `selection: provider-default`) so identities stay comparable across providers.

### Discussion with the requester and conclusions (2026-11-25)

- **Q1 what to switch to**: another CLI agent (not a direct model API). The `claude_cli.py` subprocess transport and the `submission.py` structured-submission channel remain usable.
- **Q2 must Skill/attribution follow the provider**: yes. Making the skill path provider-owned is therefore the core of this issue.
- **Q3 config entry**: via env — `Settings` gains generic `ai_agent_bin` / `ai_agent_settings`, while the old `ai_agent_claude_bin` / `ai_agent_claude_settings` remain readable as compatible aliases so existing deploy injection keeps working.
- **Q4 deployment**: out of scope; the requester will adapt the deploy pipeline when actually switching.
- **Q5 capability declaration**: promoted to an explicit protocol — the parent gains a `capabilities` class variable; `ProviderHealth` gains a structured auth field; preflight prints a capability line. Subclasses that do not declare `capabilities` keep the "derive from `run_skill` override" compatibility path.
- **prompt ownership**: we discussed keeping the `/{name}` prompt upstream while the subclass only stages files, and rejected it — the staging layout and the invocation syntax are two halves of one protocol; if the service layer keeps writing `.claude/skills` and composing slash commands, every new backend must imitate Claude. The adopted design is a **neutral skill layout**: the platform defines `work/skills/<name>/`, and the upstream prompt references that path (no slash syntax); a `stage_skill` hook lets each provider adapt the neutral layout to its best form and optionally return a "native prefix" — `ClaudeCodeProvider` creates the `.claude/skills/<name>` symlink and returns `/{name} ` (keeping the deterministic native trigger), while a generic backend returns an empty string and works with zero adaptation.
- **old snapshots and the new prompt wording**: prompts are not part of the freeze, so after the wording change even old snapshots replay with the new prompt; agent/modelIdentity checks are unaffected. Accepted as an execution-semantics evolution and recorded in the implementation PR's Agent Note.

### Requester's requirements

- When switching to a new CLI agent, **Skill / attribution must follow the provider**; no intermediate state where "the new backend does not run attribution yet".
- Config via env: support `ai_agent_bin` / `ai_agent_settings`, keep `ai_agent_claude_*` compatible.
- Promote capabilities to an explicit protocol.
- The deploy pipeline is handled separately by the requester at switch time; not part of this issue.
- Replay validation and the old-snapshot alias mapping keep their current semantics; existing snapshots must keep replaying.

## Goals

- `AIAgentProvider` gains a `stage_skill(work, name, files) -> str` hook: the provider adapts the neutral `work/skills/<name>/` layout into its own skill form and returns an optional invocation prefix; the service layer no longer contains the `.claude/skills`, `.cac/skills`, or `/{name}` literals.
- The upstream skill prompt becomes path-referencing ("Use the {name} skill: read `skills/{name}/SKILL.md` and follow it strictly…"); task text (`INSTRUCTIONS`, input-file description, platform writer contract) stays upstream.
- `AIAgentProvider` gains `capabilities: ClassVar[frozenset[str]]` (`"analyze"`, `"edit"`, `"skill"`); `supports_skills` prefers the declaration and falls back to override detection for subclasses that do not declare it; `ProviderHealth` gains a structured `auth` field (`ok` / `missing` / `unknown`); preflight prints a capability line.
- `Settings` gains generic `ai_agent_bin` / `ai_agent_settings`; the old `ai_agent_claude_bin` / `ai_agent_claude_settings` remain readable as compatible aliases; `AIAgentProvider` gains a `from_settings()` classmethod hook for backends that need extra config.
- In passing: promote `EDIT_PLAN_FILENAME` to a shared package constant (`patch_source.py` converges in the same change, its `_edit_prompt` literal becomes a reference) and move `PERMISSION_MODE` from `base.py` into `claude_code.py`.
- Update the "one subclass plus one registry entry" wording in `docs/ai-agent.en.md` / `.md` to the real touchpoint list, and add an Agent Note.

## Design authority

- [07 §5.5.1 AI Agent Provider adapter layer](../../../plans/fullstack-design/07-backend-implementation.md): the parent defines contracts only, capability faces are split by interface rather than vendor, and a future OpenCode or direct-API backend is one subclass; this issue makes that claim actually true and updates the section's extension notes (`SupportsEmbedding` etc. remain unimplemented and out of scope).
- [07 §5.5.3 structured submission channel](../../../plans/fullstack-design/07-backend-implementation.md): the submission channel is a protocol, not a vendor mechanism, shared by all CLI backends; this issue does not change its semantics.
- [07 §5.5.4 Edit-instruction patches](../../../plans/fullstack-design/07-backend-implementation.md): the EditPlan submission filename is a cross-layer contract and converges into a shared constant.

## Implementation

- `third_party_api/ai_agent/base.py`: add `stage_skill(work, name, files)` (default raises "provider does not support Skill staging"), the `capabilities` class variable (default `analyze`/`edit`), and `from_settings()` (default `cls(settings)`); `supports_skills` prefers the declaration with override detection as fallback; move `PERMISSION_MODE` out.
- `third_party_api/ai_agent/claude_code.py`: implement `stage_skill` (stage the neutral layout, create the `.claude/skills/<name>` symlink, return the `/{name} ` prefix), the explicit `capabilities` declaration, and `from_settings` with generic-field/legacy-alias normalization; adopt `PERMISSION_MODE`.
- `third_party_api/ai_agent/contracts.py`: add `auth` to `ProviderHealth` (`ok` / `missing` / `unknown`); land `EDIT_PLAN_FILENAME` as a shared package constant.
- `service/evolution/local_attribution.py`: slim `_stage_attempt` to "write case inputs → call `provider.stage_skill` → compose prefix + task text"; keep the replay alias mapping and the `skill_model_identity` equality check as-is; the execution log still records the full final prompt.
- `app/config.py`: add `ai_agent_bin` / `ai_agent_settings` with the old validation rules (blank bin fails startup, blank settings means unset); keep the old fields as deprecated aliases and normalize reads through a compatibility accessor.
- `app/main.py` and `ai_agent/preflight.py`: assemble through `from_settings()`; preflight prints a capability line (`provider=... skills=yes/no auth=ok/missing/unknown bin=present/missing`).
- `fake.py`: declare `capabilities` (no `skill`) as the minimal example of the explicit protocol.
- Tests: `stage_skill` layout and prefix, zero-adaptation onboarding of a compatible backend, explicit vs derived `capabilities`, the three `ProviderHealth.auth` states, Settings new/old name equivalence, and regression for skill execution and old-snapshot replay (including the legacy `claude` alias).
- Docs and flow: update the touchpoint list and capability protocol in `docs/ai-agent.en.md` / `.md`; record the capability protocol and skill-layout contract in 07 §5.5.1; add the Agent Note in the same PR as the implementation.

## Implementation steps

1. `base.py` / `contracts.py`: add `stage_skill`, `capabilities`, `from_settings`, `ProviderHealth.auth`, shared `EDIT_PLAN_FILENAME`; move `PERMISSION_MODE`.
2. `claude_code.py` / `fake.py`: implement the hooks and explicit declarations; normalize generic/legacy names in `from_settings`.
3. `config.py`: add the generic fields and the compatibility accessor; wire `main.py` / `preflight.py`.
4. `local_attribution.py`: slim `_stage_attempt` and switch the prompt shape; keep replay alias and identity-check semantics.
5. Add unit and API tests (neutral-layout execution, zero-adaptation compatible backend, old-snapshot replay regression).
6. Run focused gates; update `docs/ai-agent.en.md` / `.md`, 07 §5.5.1, and the Agent Note; `flow:sync` the status.

## Dependencies and boundary

- Dependencies: none open (`bugfix-17`/`bugfix-19`/`bugfix-21`/`bugfix-26` etc. are done).
- Boundary: only the `ai_agent` package, the skill-assembly section of `local_attribution.py`, `config.py` / `main.py` / preflight, tests, and docs; no changes to the `submission.py` / `edits.py` protocols, `claude_cli.py` transport semantics, the `_skill_provider` alias or modelIdentity check logic, or the eval/clustering business logic.

## Verification

```sh
pnpm lint:api
pnpm typecheck:api
pnpm test:api -- -k "ai_agent or local_attribution or preflight"
pnpm test:api:serial -- -k "attribution"
pnpm verify:flow
pnpm lint:docs
```

- Expected: `ClaudeCodeProvider.stage_skill` produces both the neutral layout and the `.claude/skills/<name>` symlink in the task directory and returns the `/{name} ` prefix; a stub backend that only declares `capabilities` passes the skill-execution tests with zero slash adaptation; with either `ai_agent_bin` or `ai_agent_claude_bin` set the provider resolves the same path, and the generic name wins when both are set; `ProviderHealth.auth` returns the right state from credential presence; preflight prints the capability line; the legacy `claude`-alias snapshot replay tests stay green.

## Acceptance

- `local_attribution.py` no longer contains the `.claude/skills`, `.cac/skills`, or `/{name}` literals; staging and invocation syntax are fully provider-owned.
- A minimal stub backend (declares `capabilities`, implements `stage_skill` with an empty prefix, reuses the `claude_cli` transport) completes analyze / edit / health / skill in tests without touching the service layer or config code.
- Missing skill capability is no longer silent: a backend that neither declares nor overrides `run_skill` reports `skills=no` in preflight while assembly behaves as today (attribution cache-only); capabilities are enumerable.
- `ai_agent_bin` / `ai_agent_settings` work with legacy compatibility: the three env combinations (old only, new only, both) are deterministic and covered by tests.
- Replay semantics do not regress: the `{"claude", "...ClaudeBackend"} → "claude-code"` alias and the `skill_model_identity` equality check keep their current behavior; existing-snapshot (including legacy-name) tests pass.
- The structured `ProviderHealth.auth` field and the preflight capability line land; merging provider health into `/api/health` is out of scope (see non-goals).
- Focused tests, `verify:flow`, and `lint:docs` pass; `docs/ai-agent.en.md` / `.md` are updated and re-recorded as a pair; the Agent Note is added.

## Gates and CI

- Hit: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm test:api:serial`, `pnpm verify:flow`, `pnpm lint:docs` (the implementation PR additionally runs `pnpm verify:docs` and `pnpm test:gates`).
- No new third-party dependencies; CI uses fake / stub providers throughout — no network, no real `claude` binary; the `HE_AI_AGENT_CLAUDE_E2E=1` real-CLI smoke stays an opt-in lane with new cases covering the neutral-layout prompt shape.

## Non-goals

- No real new backend (Codex / Gemini etc.); this issue only guarantees that "one subclass + registration + zero service-layer changes" is a working onboarding surface, verified through the stub backend.
- No deploy pipeline, install script, Secrets injection, or `docs/claude-code.md` changes (the requester handles those at real switch time).
- No changes to the `submission.py` protocol, the `edits.py` applier, `claude_cli.py` transport, or timeout-constant semantics; no per-provider timeout config and no `HE_AI_AGENT_NATIVE_SCHEMA` fast path.
- No cleanup of always-empty contract fields such as `EditResult.changed_files` / `unified_diff` (evaluated separately).
- No merge of provider health into `/api/health`; no `SupportsEmbedding`; no changes to attribution eval or the three-layer clustering logic.
