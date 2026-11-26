# Agent Note: opt-in name matching for agent evolution targets

Status: implemented

English | [中文](2026-11-26-agent-name-matching-mode.md)

## Problem

An agent evolution target's version identity is the normalized body hash of `AGENT.md`: the target resolver reads the file at the selected ref and derives `targetRevision=digest:<sha256>`, and the overview target analysis filters Sessions by event `object_revision`/`definition_hash` on each version row. An agent event stores `object_revision` as the composed `agentType + builtin marker + body hash` digest, which is not the pure body hash the target resolves; the same agent name's body also drifts across versions, trace snapshots and runtime-injected prompts. Consequently one agent name appears as several digest rows in the overview, the configured ref's row can filter down to zero Sessions by hash, while the wizard, launch and background binding already associate by object type plus name presence. The two read paths disagree.

Matching purely by name gives up version precision for same-name different bodies, so it cannot become the default; it needs an explicit, configurable, default-off exception.

## Decision

- Add `HE_AGENT_MATCH_BY_NAME` (`Settings.agent_match_by_name`, boolean, default `false`, read at startup, requires a `harness-api` restart).
- When on, it applies only to `object_type=agent`: `PotentialMatcher.associated_sessions` ignores `observed_revisions`; `TargetOverviewService` builds one version keyed and displayed by `defaultRef`, associates every Session in the window that contains the agent name, and builds historical report aliases for that row (configured ref, resolved revision, bare hash and historical report `object_version`) so `_newest_link_by_case` still selects existing reports and attributed/nonTarget counts do not drop through the version collapse.
- Report content identity, `targetRevision`, prompt freezing, run snapshots, cache keys, step-4 `reused/fresh`/`nonTargetKnown`, the launch latest-reports gate and `BindingWorker` completion dedupe still use the body hash; name matching changes only the association and version-row layer.
- Skill/knowledge targets, event ingestion, database schema and the OpenAPI contract stay unchanged; historical digest versions and reports remain readable without migration or backfill; `AGENT.md` remains required content for launch and attribution, and read failures stay explicit.

## Alternatives considered

- **Always match agents by name**: it would mix same-name different-body Sessions by default and lose the current hash-based version evidence; default-off opt-in keeps existing deployments byte-identical.
- **Change agent `targetRevision`, report cache keys or prompt freezing to the name**: reports for same-name different bodies would be reused for each other, and content identity plus the patch baseline would no longer be traceable; this decision changes only association and version rows.
- **A global "name first, hash fallback" automatic fallback**: hit behavior would depend on incidental data gaps and could not explain different outcomes for cases in one workspace; an explicit switch is auditable.
- **Keep digest versions in the overview and associate each row by name**: the same Session would count under several version rows; a single version row keeps name-mode statistics stable.
- **Add a UI switch or form field**: this is deployment-level `.env` behavior; a UI toggle would introduce per-user semantics; rejected.

## Consequences

- With the switch on, different body versions of one agent name aggregate into one overview row and version precision gives way to name association; historical reports survive through aliases, and new attributed/nonTarget counts may rise as same-name Sessions widen.
- Report caches and the latest-reports launch gate still key on the body hash, so an `AGENT.md` content change opens a new report scope; that is the intended content-identity boundary.
- The switch reads process configuration once; changing it requires restarting `harness-api`. Default off keeps behavior byte-identical.
- No database migration; historical digest versions, reports and run snapshots remain as they are. If the product later makes the name the sole identity, that needs a separate design covering report reuse and migration.
