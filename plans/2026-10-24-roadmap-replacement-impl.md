# Verifiable Roadmap Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy flow tree with six detailed, independently verifiable milestones and synchronize complete issue bodies to GitHub while retiring superseded remote objects without deleting history.

**Architecture:** The local bilingual flow tree remains the source of truth. Stable planning IDs and dependency lists are machine-checked; GitHub synchronization publishes the detailed Chinese issue body and optionally closes remote objects absent from the tree. Product implementation requirements link to the existing fullstack design rather than duplicating it.

**Tech Stack:** Markdown, YAML flow fences, Node.js 22, node:test, existing flow/i18n gates, GitHub CLI.

**Spec:** `plans/fullstack-design/README.md` and the confirmed six-milestone proposal in the task conversation.

## Global Constraints

- Do not track `claude-code-sessions/` or `data/`; local real sessions never enter GitHub issue bodies.
- Every roadmap/milestone/issue and Agent Note is a bilingual three-file pair with identical flow fences.
- Every issue states implementation, steps, dependencies, design sections, focused verification, acceptance, gates, and non-goals.
- `plans/fullstack-design` is the implementation authority; current-state docs change only when the corresponding capability lands.
- Remote retirement closes objects and never deletes issues or milestones.
- All GitHub writes go through `pnpm flow:sync`.

## Review Focus

- Missing or forward dependency: `verify:flow` must reject unknown IDs and dependency cycles before sync.
- Bilingual drift: every generated pair must pass pairing and structural checks after GitHub number backfill.
- GitHub body drift: a second sync must publish local body edits without changing issue identity.
- Over-broad retirement: only open remote objects absent from the current tree may be closed; present or already closed objects stay untouched.
- Private session leakage: generated issues contain aggregate counts and fixture policy, never raw trajectory text or local absolute paths.

---

### Task 1: Flow schema and synchronization tests

**Files:**
- Modify: `scripts/gates.spec.mjs`
- Test: `scripts/gates.spec.mjs`

- [x] **Step 1:** Add failing tests for required stable issue IDs, dependency references/cycles, detailed issue sections, GitHub body rendering, body synchronization, and retire-missing planning. Expected: tests fail because the new exports and validation do not exist.
- [x] **Step 2:** Run `pnpm test:gates`. Expected: only the new expectations fail; existing flow behavior remains green.

### Task 2: Flow schema and synchronization implementation

**Files:**
- Modify: `scripts/flow-lib.mjs`, `scripts/flow-new-issue.mjs`, `scripts/flow-sync.mjs`, `scripts/gates.spec.mjs`, `.agents/flow/README.md`, `.agents/flow/README.en.md`, `.agents/flow/README.i18n.yaml`

- [x] **Step 1:** Implement `id`/`depends`, detailed-section validation, dependency cycle detection, and generator flags/template. Expected: focused schema tests pass.
- [x] **Step 2:** Implement detailed GitHub issue body rendering/synchronization and explicit `--retire-missing` close-only behavior. Expected: focused sync tests pass.
- [x] **Step 3:** Update the bilingual flow contract and re-record it. Expected: `pnpm test:gates` and the flow pairing check pass.

### Task 3: Replace the flow tree and record the decision

**Files:**
- Delete: all legacy `.agents/flow/roadmap*`, `.agents/flow/milestones/*`, `.agents/flow/issues/*`
- Create: six milestone triplets and 41 issue triplets under `.agents/flow/`
- Create: `.agents/notes/proposed/process/2026-10-24-verifiable-roadmap*` triplet

- [x] **Step 1:** Generate the new roadmap, milestones, issues, and Agent Note with detailed bilingual content and explicit fullstack-design references. Expected: all 41 stable IDs and dependency references resolve.
- [x] **Step 2:** Re-record every changed pair. Expected: no stale i18n records.
- [x] **Step 3:** Run `pnpm verify:flow`, `pnpm test:gates`, and `pnpm verify:docs`. Expected: all pass with no legacy files or placeholders.

### Task 4: Verify and synchronize

**Files:**
- Modify: GitHub milestones/issues through `scripts/flow-sync.mjs`; local YAML backfills and pair records

- [x] **Step 1:** Inspect the complete diff and scan for placeholders/private-data paths. Expected: no `TBD`, template placeholder, raw session content, or tracked local database.
- [ ] **Step 2:** Authenticate `gh` if necessary, then run `pnpm flow:sync -- --retire-missing`. Expected: six new milestones and 41 detailed issues are created; old open objects are closed; no remote object is deleted. Blocked: current gh token is invalid.
- [ ] **Step 3:** Re-record backfilled pairs and run offline/online verification. Expected: local and GitHub states, milestone ownership, and detailed bodies agree. Blocked until Step 2.
