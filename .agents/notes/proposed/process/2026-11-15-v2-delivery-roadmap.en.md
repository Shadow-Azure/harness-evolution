# Agent Note: V2 delivery roadmap and real-trace evidence gate

Status: proposed

English | [中文](2026-11-15-v2-delivery-roadmap.md)

## Problem

PR #209 confirmed the V2 target state, but the flow tree had no implementation slices. Session ccbdb2f0 also exposed missing semantic versions, inconsistent parent relation export, a root ending on tool use, and no knowledge-document trigger model. Potential matching would otherwise rely on unreliable session evidence.

## Decision

Close M6 with its delivered integration foundation and runtime evidence, then add M7-M12. M7-M11 deliver workspace boundaries, workspace data, session evidence, attribution pipelines, and multi-attribution cutover; M12 owns live upstream, external contracts, patch/evaluation, clustering, and platform-quality debt. M9 remains the hard gate before M10 and owns revision resolution, relation confidence, execution completion, trigger coordinates, and knowledge-document evidence.

## Alternatives considered

Folding evidence work into attribution hides whether bad counts come from versions, relations, or attribution; treating every file read as knowledge usage misclassifies source browsing; relying only on object_version misses real skills represented by content digests.

## Consequences

The V2 program has five milestones instead of four. M10 cannot start before M9 P0 evidence work. Unfulfilled M6 work moves to new M12 issues, while old GitHub issues become migration records with successor links. The attached raw session is not committed; only sanitized fixtures may be derived from its shape. Knowledge documents begin as evidence objects, with evolution support decided by a later explicit boundary.
