# Agent Note: member-level name matching replaces the deployment env switch

Status: implemented

English | [中文](2026-11-27-member-name-match-switch.md)

## Problem

The version identity of a skill/agent is the body hash of its normalized definition. Same-name objects with different bodies split into multiple version rows, and the configured-ref row may have no Sessions. The previous `HE_AGENT_MATCH_BY_NAME` opt-in applied to every agent on a deployment: members of one configuration could not choose independently, skills had no entry, and a restart was required. The member editor already owns type, name, and subdirectory per member, so the switch belongs on the member rather than on the deployment.

## Decision

- Add `match_by_name BOOLEAN NOT NULL DEFAULT false` to `evolution_target_members`, persisted with member create/update; it applies only to skill/agent members, knowledge and synthesized members stay false, and historical rows are not backfilled to true.
- `MatchTarget` carries `match_by_name` and every `MatchCondition` carries per-member targets; `PotentialMatcher.associated_sessions` ignores `observed_revisions` only for enabled members and keeps body-hash filtering for the others.
- The overview chooses the single configured-ref row or the existing version rows per member; a name row's aliases cover the configured ref, resolved revision, bare body hash, and historical report `object_version`, so attributed/nonTarget counts do not drop to zero.
- `evolution_run_targets` freezes each member's `match_by_name` at admission; launch, prepare, and the background binding worker pass it from the member or snapshot, and later config edits never rewrite historical runs.
- The frontend adds a "名称匹配" switch on the member row and submits `matchByName`; `HE_AGENT_MATCH_BY_NAME`, `Settings.agent_match_by_name`, and the `main.py` wiring are removed without a replacement environment variable.
- Report content identity, `targetRevision`, frozen source, cache keys, and step-4 statistics still use the body hash; the binding batch refreshes when this field changes, but historical reports are not rewritten.

## Alternatives considered

- **Keep the deployment env and add a skill switch**: members still cannot choose independently, one edit affects the whole deployment, and a restart is still required; this conflicts with the member editor's granularity.
- **Global "name first, hash fallback"**: gives up version precision for every object and read path and breaks the "never guess a name" rule.
- **Change only the overview, not the shared matcher**: the wizard, launch, overview, and background binding would keep separate semantics, and the symptom would only disappear from one view.
- **Backfill historical members to true**: same-name, different-body members would be silently merged and audit facts rewritten; default-off explicit opt-in matches the risk boundary.
- **Use name mode for report identity and cache keys**: same-name reports would be reused across different bodies, changing report semantics and cache scope; the switch only covers association and version rows.

## Consequences

- Enabled members show larger Session and potential counts; version precision is traded for an explicit opt-in, while disabled members and historical runs are unchanged.
- Deployments that set `HE_AGENT_MATCH_BY_NAME=true` start with every member off after upgrade and must opt in per member; no automatic migration is provided.
- The switch persists with member config and needs no `harness-api` restart; toggling refreshes the binding batch without recomputing historical reports or `targetRevision`.
- Every member create/read response carries `matchByName`, and run cards show the frozen value; the frontend renders the switch only for skill/agent rows.
