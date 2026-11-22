# Structured submission channel submission.py: JSON5 collection, validation, and feedback

English | [中文](bugfix-structured-submission-channel.md)

```yaml flow
kind: issue
id: bugfix-16
milestone: bugfix
depends:
  - bugfix-15
priority: P2
status: backlog
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/pyproject.toml
  - apps/api/tests/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 495
  url: https://github.com/Shadow-Azure/harness-evolution/issues/495
```

## Background

The merged design (#487) decides that structured collection for `analyze` relies on no CLI-internal mechanism: the agent writes a lenient-literal file and our deterministic parser collects it. The channel is a provider-layer shared component used by every CLI subclass (claude-code, opencode, …) and is layer 1 of the six-layer JSON reliability defense.

## Goals

- Add `third_party_api/ai_agent/submission.py`: the `StructuredSubmission` component with a three-method contract — `prepare(task_key, output_schema) -> SubmissionPrep` (one-shot task dir, schema.json, instruction addendum, and the single tool allowlist `Write(./result.json5)`), `collect(prep, validate) -> SubmissionOutcome` (read result.json5 → lenient JSON5 parse → json-repair salvage on failure → normalize → caller's `model_validate`), and `feedback_prompt(outcome) -> str` (locateable retry text from the concrete errors).
- `SubmissionOutcome` is a three-way terminal state — `ok / invalid / missing` — carrying `parse_error` and `validation_error`.
- Add the pure-Python dependencies `json5` (pyproject) and `json-repair` (salvage).
- Unit tests: the JSON5 lenient-format matrix (comments / trailing commas / single quotes / bare keys), repair salvage, the three terminal states, feedback text naming fields and constraints, one-shot task dirs.

## Design basis

- [07 §5.5.3](../../../plans/fullstack-design/07-backend-implementation.md): channel mechanics, the six-layer defense, and the distilled value of "generate JSON with JS" (lenient literals plus deterministic serialization, never executing model code).
- The Agent Note (adr): the recorded trade-off of the self-built channel vs `--json-schema`.

## Implementation

- `prepare` isolates the task dir per call (uuid/task-key derived), never reused; `prompt_addendum` states "write conclusions into result.json5 (JSON5 lenient format); shape per schema.json".
- `collect` parses in order: strict JSON → JSON5 → json-repair (salvage); the first success proceeds to validation, with the validation exception text preserved verbatim in `validation_error`.
- `feedback_prompt` emits text like "result.json5 field X violates constraint Y — fix and rewrite" for the subclass `--resume` retry.
- The component never starts model calls, holds no business rules, and is backend-agnostic (the four "does not" boundaries).

## Steps

1. Add dependencies; implement the three methods and data classes.
2. Unit tests over the lenient-format matrix and the three states.
3. Gates: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm verify:flow`.

## Dependencies and delivery boundary

- Dependencies: bugfix-15 (package skeleton and contracts).
- Delivery boundary: only submission.py, dependencies, and tests; no subclass or business changes.

## Independent verification

```sh
pnpm test:api -- tests/test_ai_agent_submission.py
```

- The lenient-format matrix is green; malformed input always ends `invalid` or `missing` with no uncaught exception.

## Acceptance criteria

- The three-method contract and terminal states are pinned by tests; each of the four JSON5 leniencies has at least one case.
- json-repair salvage runs only as the fallback (never when strict/JSON5 parsing succeeds).
- Feedback text includes field names and constraint descriptions.
- CI green.

## Gates and CI

- api-static / unit-tests-api / docs-flow.
- Commit and PR titles carry `(#N)`.

## Non-goals

- No MCP submit-tool variant.
- No claude-code subclass wiring (bugfix-17) and no business integration.
- No `--json-schema` fast path.
