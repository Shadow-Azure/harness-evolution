# Agent Note: V2 delivery roadmap and real-trace evidence gate

Status: proposed

English | [中文](2026-11-15-v2-delivery-roadmap.md)

## Problem

PR #209 confirmed the V2 target state, but the flow tree had no implementation slices. Session ccbdb2f0 also exposed missing semantic versions, inconsistent parent relation export, a root ending on tool use, and no knowledge-document trigger model. Potential matching would otherwise rely on unreliable session evidence.

## Decision

Keep M1-M6 and add M7-M11 for workspace boundaries, workspace data, session evidence, attribution pipelines, and multi-attribution cutover. M9 is a hard gate before M10 and owns revision resolution, relation confidence, execution completion, trigger coordinates, and knowledge-document evidence. M6 continues real upstream, evaluation, and clustering delivery rather than V2 implementation.

## Alternatives considered

Folding evidence work into attribution hides whether bad counts come from versions, relations, or attribution; treating every file read as knowledge usage misclassifies source browsing; relying only on object_version misses real skills represented by content digests.

## Consequences

The V2 program has five milestones instead of four. M10 cannot start before M9 P0 evidence work. The attached raw session is not committed; only sanitized fixtures may be derived from its shape. Knowledge documents begin as evidence objects, with evolution support decided by a later explicit boundary.
