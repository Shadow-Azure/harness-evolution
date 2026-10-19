# Agent Notes

English | [中文](README.md)

A kind of design document lives here. **An Agent Note records a decision that affects this repository** — why, and what was given up — the part code and docs cannot hold. This page defines where it lives, when to write one, and its format (below).

## Layout and naming

Both coordinates of a Note are encoded in its **path** — `{lifecycle}/{class}/yyyy-mm-dd-topic.md`:

- **Lifecycle** (top-level folder) is the state; notes move between folders as state changes:
  - **`proposed/`** — a proposal reviewed before implementation, not yet (or only partly) landed.
  - **`implemented/`** — the decision shipped. The file records what was decided and rejected, and **stays in sync with the actual implementation**: when code moves, renames or changes defaults, the same change updates facts in the Note (facts only, never the decision itself).
  - **`rejected/`** — the proposal was declined. Keep it only when the reason prevents a tempting mistake; otherwise delete the file.
- **Class** (nested folder) is the kind of decision (below).
- The filename date is when the topic **was first proposed** (per git); all other history belongs to git.

Cross-references between Notes use relative markdown links, never bare descriptions or numbers — mechanically checkable and stable across moves. There is no central INDEX.md; the directory tree is the list.

## Classes (closed set)

| Class | Coverage |
|---|---|
| `feature` | New user-visible capability |
| `bug-fix` | Fix a defect or a gap exposed by a postmortem |
| `simplification` | Remove code/behavior/surface without adding capability |
| `architecture` | Structural decisions about **shipped source** |
| `process` | Tools/policy/process around the code — gates, package management, release |
| `testing` | Test infrastructure and strategy |

The `architecture`/`process` boundary: the former concerns the source we ship, the latter the tools and process around it. Adding a class changes both the set in [scripts/verify-agent-notes.mjs](../../scripts/verify-agent-notes.mjs) and this table.

## When to write

**Every non-trivial change adds or updates at least one Agent Note in the same PR.** Non-trivial = changes behavior, architecture, cross-file contracts, process/tooling, test strategy, or any decision the maintainer may revisit. Updating an existing owning Note satisfies this; never create duplicates. Purely mechanical local edits are exempt.

Archive: an implemented note with low future value may be frozen into `archived/{class}/`. **The semantic judgment is human** — decide case by case; length and age only help discovery, never define the standard, and nothing is archived to fill a quota. The mechanical part runs through `pnpm archive:note -- <base.md>`: move the trio, set `Status` to `archived`, and record each file's sha256 in the append-only `.agents/notes/archived/manifest.json` (add-only, never modify or delete; removal or unsealing requires explicit rationale in the PR). Frozen artifacts leave live-corpus checks such as pairing, fence compilation and links — changing one byte turns red.

## File format

The first three lines are fixed, followed by a blank line:

```markdown
# Agent Note: <标题>

Status: <status>
```

`Status` is one of three, and must match the containing folder (gate-checked):

- `Status: proposed`
- `Status: implemented`
- `Status: rejected — <one-line reason>`

Skeleton: `## Problem` (motivation that stands without the solution) → `## Decision` (the decision) → `## Alternatives considered` (rejected options and why — the core reason this layer exists) → `## Consequences` (outcomes and debts). Section names are fixed; free technical sections may appear between them.

## Gates

`pnpm lint:docs` runs [scripts/verify-agent-notes.mjs](../../scripts/verify-agent-notes.mjs): legal path (lifecycle × class closed sets), first-three-lines format, `Status` matching the folder, the four-section skeleton (verbatim names, `Problem` first, on both sides), and reachable cross-links; archived artifacts are frozen-checked separately by [scripts/verify-archived-agent-notes.mjs](../../scripts/verify-archived-agent-notes.mjs) (sha256 + append-only, also in lint:docs).
