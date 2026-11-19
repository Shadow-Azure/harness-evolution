# Agent Note: target-card version rows show refs and short commits

Status: implemented

English | [中文](2026-11-19-target-version-ref-labels.md)

## Problem

Target-overview version discovery treated `agent_events.object_version` and `object_revision` as separate versions, so `main` and `digest:8e54…` from one trigger record split into two rows in Single evolution-target analysis, and production showed only the content digest. Users could not map a version row back to the tag, branch, or commit they selected, nor read the potential bad-case distribution by version.

The matching and attribution identity is the content body hash, not the ref, and refs move. The display layer needs "which ref this version evidence came from and which commit it resolved to", not a redefinition of identity.

## Decision

Target-card versions aggregate by **trigger record**: a ref and a digest in one record are two identities of one version. The digest remains the canonical key for filtering, matching, coverage counts, and statistics; the ref is only the primary display label. Identical digests across records merge; the ref is taken from the latest run's `target_version`, otherwise the target's `defaultRef`, otherwise a deterministic ref in natural order.

Commits come only from `evolution_runs.base_commit`, associated by `target_revision` first and `target_version` second, shortened to seven characters. When the default ref and a digest are linked only by a run (the events carry only the digest), the run's ref↔digest relation also merges them so no zero-row default ref remains. Digest-only records without run evidence are not backfilled from git and keep the digest fallback; legacy ref-only records keep the ref version.

Beyond `versions`, the API adds `versionOptions: [{version, ref, commit}]`, and detail rows also carry nullable `ref` / `commit`. The frontend renders the ref plus a faint short commit from `versionOptions`; checkbox values, URL state, and filter parameters keep using the canonical key. Old URLs that select a version by ref map back through aliases.

## Alternatives considered

- **Use the ref as the canonical key**: refs move, so different commits of one branch would merge incorrectly, and matching and caching are digest-based today; the change would leak into Session association and attribution semantics. Rejected.
- **Resolve a ref's current content hash in the display layer**: it saves a cache write but guesses historical digests as the current ref, and the label becomes wrong once the ref moves; only run/trigger evidence is reliable. Rejected.
- **Truncate the digest into a short summary**: it shortens the text but still leaves no tag or commit mapping, so the information gap remains. Rejected.
- **Look up a git ref for every digest**: it needs extra repository access and failure paths, and history may have no matching ref; the current need accepts the digest fallback. Rejected.

## Consequences

- The `versions` list and URL filter values unify from "ref or digest" to the canonical digest; old links map through aliases, but a person reading the URL directly sees digests.
- The target card, side list, and potential bad-case list use the ref as the primary version label; without ref evidence they still show the digest.
- The `evolution_runs` query is read-only and bounded; targets without run records have no commit and show only the ref or digest.
- When one digest maps to several refs, only one ref (latest run first) is displayed and the version is not duplicated; showing every ref is not supported today.
