# Agent Note: Four structural decisions for real-model self-evolution

Status: proposed

English | [中文](2026-11-22-evolution-real-ai-design.md)

## Problem

Clustering, confidence, severity, and patch generation in the self-evolution loop are placeholder implementations (lexical clustering, fixed confidence, constant formulas, placeholder patches). Wiring in real model capability forced four structural decisions: where outbound model calls converge; at which layer the model participates in clustering and how it scales with the volume of attribution reports; how structured JSON conclusions are collected reliably; and what representation edit patches use. The finalized design of 2026-11-22 ([07 §5.5.1–§5.5.4](../../../../plans/fullstack-design/07-backend-implementation.md)) locks in four answers; this note records why, and what was rejected.

## Decision

- **Outbound model calls converge on the `third_party_api/ai_agent` parent interface**: two capability faces (`analyze` / `edit_workspace`) plus a factory selecting a subclass by `AI_AGENT_PROVIDER` (currently only claude-code and fake); interfaces are split by capability, not vendor, so switching backends means adding a subclass. This is not a revival of the early "unified Provider layer" — it serves exactly one seam, model egress.
- **Clustering splits into three layers with LLM input/output decoupled from the attribution-report volume N**: a grouping layer at O(N) with no LLM (lexical first, vectorization as the upgrade slot); a review layer at O(K×s) doing merge/naming only (draft-key references plus the draft-partition integrity gate); a scoring layer at O(K×s) with direct cluster confidence and severity dimensions. Case-level confidence stays a rule-based signal — per-case blind scoring loses cross-case corroboration and costs O(N).
- **Structured collection goes through a self-built submission channel**: the agent writes `result.json5` (JSON5 lenient literal), and `submission.py` parses deterministically, validates, and retries with error feedback; no CLI-internal mechanism is relied upon (Claude Code's `--json-schema` is demoted to an optional fast path, off by default). The value of "generate JSON with JS" is distilled into lenient literals plus deterministic serialization, without executing model code.
- **Patches use SkillOpt-style Edit instructions**: after read-only exploration the agent submits an EditPlan (op/file/target/content/rationale); anchors must exist and be unique (ambiguity is fed back); `edits.py` applies deterministically with `git diff` as the single truth; `edit_budget` is enforced twice (prompt constraint plus hard truncation); after a reject, `--resume` continues the same session with feedback and a rejected-edit buffer. The agent tool surface shrinks to read-only plus writing one json5 — no file-edit permission.

## Alternatives considered

- **Per-case model confidence (before clustering)**: fits the attribution evidence cache naturally, but single-case blind scoring loses the corroboration effect and costs O(N); replaced by rule signals plus cluster-level direct scoring, with per-case model scoring kept as a budget switch.
- **Relying on the `--json-schema` native channel as the main path**: maintenance-free and reliable on Claude Code, but a CLI-internal mechanism — switching to opencode-like backends would crater layer-1 strength and require rewriting the feedback loop; demoted to an env-gated fast path.
- **Direct agent file editing with diff collection**: stronger for complex refactors, but intent is uncountable and it needs the acceptEdits permission surface; targets are skill/config documents (the instruction-style home turf), so direct editing stays a future switch.
- **Having the agent call a JS script to produce JSON**: the data still has to be hand-written by the model as arguments or files, or model code must be executed; replaced by "write a lenient literal, parse deterministically", keeping scripts only as a content-computation tool shape.

## Consequences

- The design has landed in `plans/fullstack-design` (07 §5.5.1–§5.5.4, the 04 tree and seam table); follow-up implementation issues use it as the design basis, and this note syncs status and facts as landing proceeds.
- Implementation proceeds in stages (skeleton → three clustering layers → optional vectorization → instruction-style patch), each reversible via env (fake / placeholder); the worst case equals today's behavior.
- Adds the pure-Python dependency `json5`; `edit_workspace` semantics shift from "edit directly" to "submit a plan, apply deterministically" — no in-turn trial loop, compensated by the turn-level iteration loop.
- The contrast between the declared intent (EditPlan) and the actual diff becomes a per-turn audit signal; any mismatch is a quality alarm.
