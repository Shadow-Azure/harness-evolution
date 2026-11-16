# Agent Note: Object revision parsing and trigger coordinates

Status: implemented

English | [中文](2026-11-16-object-revision-trigger-coordinates.md)

## Problem

Real Claude Code sessions do not always carry a semantic version: a Skill listing may expose only a name, a content summary, and an opaque 16-hex digest, while the Skill body is visible only through the `isMeta + sourceToolUseID` injection. A subagent definition body lives in `prompt_snapshot.systemPrompt[0]`. M9-01/M9-02 already parsed those bodies into hashes, but the event table only stored `definition_hash`; it had no object revision, `object_version`, `triggered_at`, or stable `tree_index`. A later PotentialMatcher could therefore compare only `targetVersion` or a name, missing objects represented only by a body or digest and losing the stable “object entry point precedes the bad-case trigger” order.

## Decision

- Migration `0017` adds coordinate columns only: `agents.tree_index` (non-null, default 0), `agent_events.triggered_at`, and `agent_events.object_version`, plus `(agent_id, triggered_at)` and `(agent_id, kind, name, object_version)` indexes. It keeps the 0016 existence guard so a partially applied MySQL DDL retries cleanly, and uses SQLite batch mode for downgrade.
- An object revision has exactly three shapes: `tag:<tag>`, `digest:<sha256>`, and `unknown`. Explicit `tag` or `version/skillVersion/agentVersion` metadata produces a tag, and a tag always wins. Without a tag, a body hash or listing digest is used; without either the value is explicit `unknown`, never inferred from a name, description, or default branch.
- A Skill revision digest binds `source_path + normalized body hash`, not the body hash alone: the same body copied to another path is a different object, while the same path and body stay stable across sessions and tasks. `definition_hash` keeps describing only the body hash; neither overwrites the other.
- An Agent revision is a digest over `agentType + isBuiltIn + systemPrompt[0] body hash`. A builtin Agent has no body but keeps its type and builtin marker; a non-builtin Agent without a body stays `unknown`. The parent `kind=agent` event receives the child transcript revision during tree assembly, and an explicit tag on the parent call still wins.
- A `skill_listing` 16-hex digest is a fallback only: supported observed shapes are a `digests` map/array, a `skills[]` list, and a single-name top-level `digest`. The algorithm is never inferred, and a body hash always wins over the listing digest.
- `triggered_at` comes from the `timestamp` of the assistant record that carries the trigger `tool_use`, normalized to Asia/Shanghai; a missing timestamp stays NULL. `tree_index` is assigned after assembly in DFS preorder (parent before child, siblings by `sort_key`), and workflow/synthetic nodes keep a coordinate too.
- `attributionSkill` stays supplementary parse evidence and is never synthesized into `agent_events`: an explicit `Skill` call is the only trigger. When there is no explicit call, no event is better than presenting an attribution marker as a trigger point. The raw payload remains in `trajectory_payloads`; no undesigned column is invented.
- `ClaudeCodeTraceParser.parser_version` advances to 4 and replays only claude-code. Existing `source_records` catch up on the next sync or `pnpm data:replay:sessions`. The Skill-definition hash mapping moves from `agent_tree` into the parser’s `finalize`, leaving one writer.

## Alternatives considered

- **Store only the body hash as the revision**: the same definition body at two Skill paths would merge incorrectly, failing the “path + body hash” identity.
- **Treat the listing digest as a primary key**: its algorithm is unconfirmed; using it as a key would push an unverifiable summary into Session association and cache keys. It remains a fallback only.
- **Write attributionSkill as a synthetic skill event**: it has no stable tool-use identity and would pollute trigger coordinates and the “explicit trigger” contract.
- **Compute tree_index/triggered_at in the read API**: the read path lacks the full parent/child shape and `sort_key`, and would recompute on every read. Persisting once through replay gives stable comparison.
- **Add a source_path column to agent_events**: the M9-02 review kept path/range in parser evidence, and M9-05 owns knowledge `source_path`; this slice does not pre-empt that column.
- **Backfill tree_index with SQL in the migration**: DFS needs the assembled parent links and `sort_key`; the migration cannot compute it reliably, so legacy rows stay 0 until replay.

## Consequences

- A Session that has not been replayed has `tree_index = 0` for every Agent and NULL `triggered_at/object_version`. Consumers must treat that as unknown coordinates: 0 is not a stable “main Agent” order, and NULL must not satisfy an “after” comparison.
- Every explicit trigger now has a revision value; an `agent` event whose child transcript is missing remains `unknown` and never guesses a definition version from `subagent_type`.
- The listing digest algorithm is still unconfirmed; it is stored but not used for matching. M10 decides later whether it can become a comparable identity.
- `attributionSkill` has no dedicated column; if M10 needs statistics by attribution marker, it must add a design and migration rather than reusing `agent_events`.
- `object_version` accepts explicit metadata only. Objects with the same name but no version are still skipped and counted at the potential-matching boundary, which is the intended safety edge.
