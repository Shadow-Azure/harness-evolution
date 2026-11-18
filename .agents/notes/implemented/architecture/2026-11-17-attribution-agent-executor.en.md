# Agent Note: Attribution Agent Executor Contract Seam

Status: implemented

English | [中文](2026-11-17-attribution-agent-executor.md)

## Problem

The intranet LLM and Agent are unavailable, but placing their future invocation directly in the Runner would couple Skill resolution, input assembly, remote execution, output validation, caching, and persistence in one transaction path. Local development and CI would also be unable to prove that a real engine replacement still honors report and evidence contracts.

## Decision

Introduce versioned `AttributionExecutorRequest` and `AttributionExecutorResponse` contracts. The input distinguishes the selected target introduction coordinate from the Badcase report coordinate and carries only bounded Session context, evidence references, and an immutable Skill revision. `agent-skill-stub-v1` uses the same protocol for deterministic execution with no network, files, or model, then projects schema-validated output into the existing `AttributionResult` and Probe Report V2. Run launch selects the engine from the effective Skill executor type, and the Runner loads content by the frozen key/revision/hash instead of consulting the current binding. A real `agent` executor is rejected at launch while its adapter is absent.

## Alternatives considered

Making the stub directly reuse `rule-v1` was rejected because it would hide that executor input/output and Skill content were not actually connected, so the stub has an independent engine key and cache identity. Sending the complete raw Trace to the executor was rejected because it expands privacy, payload, and cache surfaces; only the bounded m12-18 context is passed. Copying Skill content into every Run would add sensitive configuration and migration cost; immutable revisions already provide verifiable historical addressing, so runs freeze identity and resolve by that identity.

## Consequences

The intranet adapter can implement the same executor protocol and register an engine key without changing the Runner, repository, or report write path. Stub reports always carry `AGENT_EXECUTOR_STUB` and add a warning when full context is absent, so they cannot be mistaken for real attribution quality. The executor currently has no timeout control or model-configuration fingerprint; a remote adapter must add timeout, retry, credential injection, and a non-`none` model fingerprint outside this seam.
