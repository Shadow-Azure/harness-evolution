# Agent Note: Portable AI agent backends — neutral skill layout, explicit capabilities, and a generic config entry

Status: implemented

English | [中文](2026-11-25-portable-ai-agent-backend.md)

## Problem

The outbound layer `third_party_api/ai_agent` claims in docs and 07 §5.5.1 that "switching AI agents means one subclass plus one registry entry", but a per-operation audit showed the claim only holds when the backend runs analyze / edit / health only. The requester requires Skill / attribution to follow the provider switch, while at least three vendor assumptions leaked outside the subclass: the skill staging layout (`.claude/skills` plus the `.cac/skills` alias) and the invocation syntax (the `/{name}` slash command) lived in the service layer `local_attribution.py`; the config namespace was Claude-bound (only `ai_agent_claude_bin` / `ai_agent_claude_settings`); capabilities were derived implicitly from "did the subclass override `run_skill`", and auth state was outside the contract (`ProviderHealth` carried only `healthy` plus free text, and Claude reported healthy without credentials). A CLI agent that does not understand `.claude/skills` and has no slash mechanism cannot receive the skill package even with a correct `run_skill`.

## Decision

- **Neutral skill layout + `stage_skill` hook**: the platform defines the neutral `work/skills/<name>/` layout, and the upstream task text became a path reference (no slash syntax); the provider adapts the neutral layout into its own form in `stage_skill` and returns an optional native prefix. `ClaudeCodeProvider` links `.claude/skills/<name>` (falling back to a full-tree copy where the host refuses symlinks) and returns `/{name} `, while a generic backend returns an empty string and works with zero adaptation. The service `_stage_attempt` is now "verify frozen files → call `stage_skill` → swap in the platform writer contract → write case inputs", with no vendor literals left.
- **Capabilities promoted to an explicit protocol**: `capabilities: ClassVar[frozenset[str]]` (`analyze`/`edit`/`skill`) wins; subclasses that never declared keep the "derive from the `run_skill` override" compatibility path. `ProviderHealth.auth` (`ok`/`missing`/`unknown`) joined the contract, and preflight prints a `provider=… skills=… auth=… bin=…` capability line (`bin=present` ⇔ `auth ∈ {ok, missing}`, i.e. a working binary was probed).
- **Generic config entry**: `Settings` gains `ai_agent_bin` / `ai_agent_settings` (the generic names use `None` for "unset"); reads normalize through `effective_ai_agent_bin` / `effective_ai_agent_settings` — legacy only, generic only, and both set are all deterministic (generic wins). The old `ai_agent_claude_*` fields stay as deprecated aliases with the legacy validation rules (blank bin fails startup, blank settings means unset). Assembly goes through `from_settings()`.
- **Contract debts in passing**: `EDIT_PLAN_FILENAME` converged into a package-level shared constant in `contracts.py` (`claude_code` re-exports it for the old import path); `PERMISSION_MODE` moved from `base.py` into `claude_code.py`.

## Alternatives considered

- **Keep the slash-command prompt upstream and have the subclass only stage files**: the staging layout and the invocation syntax are two halves of one protocol; if the service layer keeps writing `.claude/skills` and composing `/{name}`, every new backend must imitate Claude. Rejected.
- **Make `base.stage_skill` default to "write the neutral layout + empty prefix"**: that would let generic backends onboard with zero code, but a default that raises (`provider does not support Skill staging`) matches the direction of making `supports_skills` explicit — missing capabilities should surface instead of degrading silently (silent degradation is exactly what motivated this issue). A generic backend writes its own five-line zero-adaptation implementation. Rejected the working default.
- **Give the generic bin field a default and detect "set" by "value ≠ default"**: the old and new defaults are identical, so value comparison cannot distinguish "explicitly set to the default" from "unset". The generic names use `str | None = None` to preserve provenance, making all three combinations strictly decidable. Rejected value comparison.
- **Add a structured binary field to ProviderHealth for the capability line**: `auth=unknown` already implies "the probe never reached a working deployment", so `bin` derives from `auth` and the contract does not grow for one display token. Rejected the extra field.
- **Patch `AgentBackend` (the legacy plugin base) with `stage_skill`**: the file is outside this issue's scope, and the only in-repo identity of legacy plugin snapshots is already covered by the `{"claude", "...ClaudeBackend"} → "claude-code"` alias. Arbitrary `module:Class` plugin snapshots now fail loudly before staging — acceptable semantic evolution. Rejected going out of scope.

## Consequences

- Old snapshots replay with the new task text: prompts are not part of the freeze, the `agent` / `modelIdentity` checks are unaffected, and this is an accepted execution-semantics evolution; the `{"claude", "...ClaudeBackend"} → "claude-code"` alias and the `skill_model_identity` equality check keep their exact semantics, so existing-snapshot (including legacy-name) tests stay green.
- The case-tools mode (Linux with bwrap disabled) now reads the frozen `SKILL.md` from the neutral layout: the anti-symlink-escape guards in `attribution_case_tools` and `claude_skill._case_tool_options` run on the neutral layout (all real files), while the vendor link only serves the CLI's own skill discovery.
- Preflight now probes the provider with a ≤10s timeout (a real backend runs one `--version`): the capability line's `auth`/`bin` come from that probe, and the release script's existing verdict tokens (`ready=True` / `cache_only=True` / `ATTRIBUTION_*`) are unchanged.
- The `docs/ai-agent.md` word budget moved from 850 to 1000: the touchpoint list, capability protocol, and generic config names are resident facts, and compressing them would lose the operational "what to touch when switching" value.
- Switching to a real new backend still requires syncing the deploy pipeline and Secrets injection (the requester owns that; this issue does not touch `deploy/`).
