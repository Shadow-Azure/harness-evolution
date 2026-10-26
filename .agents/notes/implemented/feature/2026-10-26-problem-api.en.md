# Agent Note: Read-only Problem and Attribution API

Status: implemented

English | [中文](2026-10-26-problem-api.md)

## Problem

Problem lists, deep-link details, and probe reverse reads need both normalized Agent trees and the three external problem tables. Separate queries can assemble mixed versions; per-problem queries cause N+1 reads and let the tree and problem APIs drift into different anchor rules.

## Decision

Five read-only endpoints share one `ProblemRepository` database-session snapshot: Session, Agents, events, problems, analyses, and probes are read first and composed in memory. `ProblemService` reuses `BadCaseService` display-state and drift validation and calls the same anchor resolver as the Session tree.

Problem detail and attribution accept an optional `sessionId` as deep-link ownership evidence; mismatch returns `409 BAD_CASE_SESSION_MISMATCH`. Missing problems and probes use stable 404 codes, while missing attribution remains a normal `unanalyzed` placeholder. A main-Agent reporter exposes `agentId=null`; an unknown non-main reporter keeps its external id and safely degrades the anchor to main. When an analyzed result no longer matches its status-specific shape, the public response degrades to `unanalyzed`. Presentation-enum drift keeps a visible problem card marked by `degraded=true` and a stable `diagnosticCode`, anchored to main/-1.

## Alternatives considered

- Query analysis and probes per problem: rejected because it introduces N+1 reads and can mix versions.
- Compare Session ownership in the browser: rejected because the backend must own cross-Session semantics.
- Return 404 for missing attribution: rejected because unanalyzed is a valid business state.

## Consequences

Problem reads remain read-only and internally consistent; malformed external rows affect only their own presentation and cannot become a page-wide 500 or silently disappear. The error-detail page remains owned by a later issue. Any new problem or anchor field must update shared schemas, generated contracts, and both tree/problem paths so semantics cannot diverge.
