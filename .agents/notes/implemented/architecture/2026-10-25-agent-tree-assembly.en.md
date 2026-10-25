# Agent Note: Agent Tree Assembly Boundary

Status: implemented

English | [中文](2026-10-25-agent-tree-assembly.md)

## Problem

Per-payload normalization yields independent nodes. Without parent-call links before persistence, ordinary Agents, Workflows, teammates, and forked skills become flat records that cannot be traced back to a root.

## Decision

Tree assembly is a pure function over normalized results. Every root has exactly one main; an ordinary subagent links through `toolUseId` to its parent Agent call, a teammate links to main, a forked skill links through its Skill trigger, and a Workflow trigger creates a zero-statistics synthetic node. Missing or unknown parent calls retain the node, degrade it to main, append a deterministic synthetic `agent` edge anchor to main, and emit warnings containing only identity, line, stable code, and fixed text. Parent-chain validation and cycle detection run before canonical structural-depth, source-position, and id ordering; public `spawnDepth` keeps the provider value and structural depth is never written back.

Node statistics copy parser results and session statistics sum the complete tree; `agents_count` includes only non-forked subagents. User turns come from main, models and Skill names are deduplicated, any error block makes the session `partial`, and a main without assistant messages is `fail`. Session bounds cover every timestamped transcript and must be non-null; the full title retains the first user prompt while `shortTitle` alone is display-truncated; `searchText` is lowercase title plus repo; a matched parent trigger supplies subagent/fork descriptions and forked skill nodes omit meta names. This slice provides only pure trees and local aggregation, not business-table writes, `source_records.processed_*`, or full replay.

## Alternatives considered

- Write trees during normalization: one payload failure crosses transaction boundaries and prevents unified missing-parent and cycle checks.
- Drop a subagent with a missing parent: this would reduce replayable nodes below all 62 real local subagents and hide provider anomalies.
- Create a node for every ordinary Skill: this conflicts with forked-skill transcript semantics and fabricates Agents.

## Consequences

Local verification must keep four roots, 66 nodes, and all 62 subagents traceable while reporting a missing-parent warning. m2-05 can reuse the immutable node result for transactional delete-and-rewrite; contract or statistic changes require a new assembler contract and golden fixtures.
