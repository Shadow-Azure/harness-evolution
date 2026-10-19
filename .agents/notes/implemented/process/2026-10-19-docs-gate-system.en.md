# Agent Note: Documentation, review and flow gate system

Status: implemented

English | [中文](2026-10-19-docs-gate-system.md)

## Problem

The repository already had a web and server scaffold, but docs, development flow and review still relied on conversation memory: phase goals had no commitment surface, changes had no task boundary, document structure drifted easily, and PR review had no stable evidence or triage rules. The proven documentation engineering, gate engineering and PR review system from StudyWiki needed to move here and adapt to the `apps/*`, `packages/*` monorepo layout.

## Decision

- Documentation follows "one fact, one home": current state in `docs/`, decision rationale in `.agents/notes/`, development flow in `.agents/flow/`, incident narrative in `docs/postmortem/`.
- Resident docs use a Chinese-English trio with hash records; structural mirroring, link locale and switcher lines are mechanically checked by `verify-translation-pairing`.
- Development flow uses roadmap → milestone → issue → ADR; machine fields live in a `yaml flow` fence; issue ids couple to GitHub numbers, and `bootstrap: true` is reserved for the first milestone's self-bootstrapping issue.
- Gates have two modes: `doc-quick` covers index, budgets, wrapping, pairing, terminology, type-equiv, export docs and source references; `doc-sync` adds real ts-fence compilation, dead links and gate self-tests.
- Port `pr-review`, `pr-review-fix`, `computer-use`, `computer-use-smoke-reporting` and the walkthrough metadata skill; review documents live in `plans/` and never enter Agent Notes.
- The scan surface moves from StudyWiki's `src/` to `apps/*/src` and `packages/*/src`; Tauri, Rust, artifact-link and walkthrough-specific gates are dropped, keeping only what matches this stack.

## Alternatives considered

- Copy scripts without the documentation contract: gates would not explain why they are red, and maintainers would treat exemptions as the default path; rejected.
- Keep documentation Chinese-only: the reference project's pairing gate and re-record tooling carry full value, and monolingual docs would disable structural mirroring and the terminology supply chain; rejected.
- Keep a second `docs/roadmap.md`: it would form a dual source of truth with `.agents/flow/roadmap.md` and inevitably drift; rejected, only the flow-tree version remains.
- Port every StudyWiki gate: Tauri artifacts, the Rust command catalog and the walkthrough site have no counterpart here, and empty runs only create noise; rejected.

## Consequences

- The smallest documentation change becomes "edit both sides + re-record"; the first setup costs more, but later drift is mechanically visible.
- `flow:sync` and `verify:flow-online` require a logged-in `gh`; the m0 issue bootstraps with `bootstrap: true`, and the first sync backfills its number and removes the flag.
- Gate self-tests use Node's built-in `node --test` and add no dependency; new gate leaves must update both `run-gates` and the self-tests.
- The walkthrough site and release pipeline are not ported; if needed later, add them incrementally under the same layering and gate pattern.
- Debt: m1–m3 issues need refinement with the first vertical slice; the PR review template has not yet been exercised on a real PR.
