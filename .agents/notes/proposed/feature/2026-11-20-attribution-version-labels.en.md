# Agent Note: Attribution-list version label shows ref / commit

Status: proposed

English | [中文](2026-11-20-attribution-version-labels.md)

## Problem

The Session error view's attribution list renders only `probe_reports.object_version`. When an object version has only `digest:<sha256>` evidence, the 71-character version cannot shrink or ellipsize in the narrow sidebar; it squeezes the object name to zero width and overlaps the "cached / attributed" badges. The overview version row already shows ref + short commit via m17 ([2026-11-19-target-version-ref-labels](../../implemented/bug-fix/2026-11-19-target-version-ref-labels.en.md)), but the attribution-list contract has no ref / commit and offers no full-value affordance or copy entry. The V2 prototype samples use short tags, so their default state hides the problem.

## Decision

The attribution item prefers the readable ref + short commit (matching the overview), falls back to the short commit when only a commit exists, and keeps a digest fallback when only digest evidence exists. The version area shrinks and ellipsizes; hover or focus reveals the full value above it, and the adjacent copy button copies the full version identifier (commit first, digest fallback). The production `AttributionItem` gains nullable `objectRef` / `objectCommit`, populated from the run's `targetVersion` / `targetRevision` / `baseCommit`; the digest remains the canonical matching and cache key and is only a display fallback. The V2 prototype lands first; the production API and frontend follow under the same issue.

## Alternatives considered

- Truncate the digest without switching to ref / commit: removes the overlap but keeps two different display conventions between the overview and the attribution list, despite the server already holding a readable ref.
- Reverse-lookup git refs for historic digests: requires walking refs and content hashes per repository, with high cost and uncertainty; m17 already ruled this out.
- Wrap the version onto a second line: accommodates long values but turns the attribution item from two lines into three, reducing sidebar density and changing its rhythm.
- Native `title` only: cheapest to implement, but the delay and position are uncontrolled, unstable inside scroll containers and zoom, and cannot carry a copy action.
- Put ref / commit into the cache key: changes attribution reuse semantics and exceeds the display-layer scope.

## Consequences

Production needs one contract and read-path change (the API backfills ref / commit) plus one frontend component update. Historic digest-only attributions still show a truncated digest without losing data or reverse lookups. The prototype fixes the interaction (truncation, layer above, copy) with Before / After evidence; the production implementation must be comparable in the same region. Attribution matching, cache keys, pagination, and statistics stay unchanged. Production screenshots and user Session content do not enter the repository.
